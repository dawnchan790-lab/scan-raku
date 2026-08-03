"""コマンドラインインターフェース。

    python3 -m fmbill torikomi   注文.txt          # 取り込み → 仕分け帳へ
    python3 -m fmbill shiwake    --month 2026-08   # 仕分け帳をExcelで確認
    python3 -m fmbill nyuryoku                     # 納品数量の入力画面を開く
    python3 -m fmbill shiwakehyo --date 2026-08-07 # 仕分け表（ピッキング用）を作成
    python3 -m fmbill nouhin     --date 2026-08-07 # 納品書を作成
    python3 -m fmbill seikyu     --month 2026-08   # 20日締めの請求書を作成
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from .app import AppContext
from .billing import build_delivery_note, build_invoice, closing_period
from .excel import TemplateWriter, delivery_note_payload, invoice_payload
from .parser import OrderParser
from .reports import export_sorting_ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fmbill", description="ファミリーマート納品・請求システム")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("torikomi", help="FAX/LINEのテキストを取り込んで仕分け帳に登録")
    p_import.add_argument("path", nargs="?", help="テキストファイル。省略時は標準入力から読み込み")
    p_import.add_argument("--source", default="line", choices=["line", "fax", "manual"])
    p_import.add_argument("--store", help="店舗コード。本文から店舗名が読めない場合に指定")
    p_import.add_argument("--date", help="納品日 YYYY-MM-DD。本文から日付が読めない場合に指定")
    p_import.add_argument("--dry-run", action="store_true", help="保存せず結果だけ表示")

    p_ledger = sub.add_parser("shiwake", help="仕分け帳をExcelに出力")
    p_ledger.add_argument("--month", help="締め年月 YYYY-MM（既定は当月）")
    p_ledger.add_argument("--store", help="店舗コードで絞り込み")

    p_note = sub.add_parser("nouhin", help="納品書を作成")
    p_note.add_argument("--date", required=True, help="納品日 YYYY-MM-DD")
    p_note.add_argument("--store", help="店舗コード。省略時はその日の全店舗ぶん")

    p_pick = sub.add_parser("shiwakehyo", help="仕分け表（倉庫のピッキング用）を作成")
    p_pick.add_argument("--date", required=True, help="納品日 YYYY-MM-DD")

    p_web = sub.add_parser("nyuryoku", help="納品数量の入力画面をブラウザで開く")
    p_web.add_argument("--port", type=int, default=8765)
    p_web.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")

    p_inv = sub.add_parser("seikyu", help="請求書を作成（20日締め）")
    p_inv.add_argument("--month", required=True, help="締め年月 YYYY-MM")
    p_inv.add_argument("--store", help="店舗コード。省略時は全店舗ぶん")
    p_inv.add_argument("--issue-date", dest="issue_date", help="発行日 YYYY-MM-DD（既定は締め日）")
    p_inv.add_argument("--due", help="振込期日 YYYY-MM-DD")

    args = parser.parse_args(argv)
    ctx = AppContext()

    handlers = {
        "torikomi": _cmd_import,
        "shiwake": _cmd_ledger,
        "nouhin": _cmd_delivery_note,
        "nyuryoku": _cmd_input_screen,
        "shiwakehyo": _cmd_picking,
        "seikyu": _cmd_invoice,
    }
    return handlers[args.command](ctx, args)


def _cmd_import(ctx: AppContext, args) -> int:
    if args.path:
        text = Path(args.path).read_text(encoding="utf-8")
        source_ref = Path(args.path).name
    else:
        text = sys.stdin.read()
        source_ref = ""

    result = OrderParser(ctx.stores, ctx.products).parse(
        text,
        source=args.source,
        source_ref=source_ref,
        default_store_code=args.store,
        default_date=_parse_date(args.date) if args.date else None,
    )

    print(f"読み取り: {len(result.orders)}件の注文 / 明細{result.line_count}行")
    for order in result.orders:
        store = ctx.stores.get(order.store_code)
        print(f"  - {order.delivery_date:%Y/%m/%d} {store.display_name}: {len(order.lines)}行")
        for line in order.lines:
            mark = "  " if line.matched else "★"
            print(f"      {mark} {line.item_name} {_fmt_qty(line.qty)}{line.unit}")

    for warning in result.warnings:
        print(f"  [注意] {warning}")

    if args.dry_run:
        print("（--dry-run のため保存していません）")
        return 0

    saved = ctx.ledger.add_orders(result.orders)
    skipped = len(result.orders) - len(saved)
    print(f"仕分け帳に保存しました: {len(saved)}件" + (f"（重複スキップ {skipped}件）" if skipped else ""))
    return 1 if result.unmatched_count else 0


def _cmd_picking(ctx: AppContext, args) -> int:
    from .picking import build_picking_tables, export_picking_sheet

    delivery_date = _parse_date(args.date)
    orders = ctx.ledger.orders_on(delivery_date)
    if not orders:
        print(f"{delivery_date:%Y/%m/%d} の納品数量がありません。")
        return 0

    tables = build_picking_tables(delivery_date, orders, ctx.stores, ctx.products)
    out = ctx.output_dir / f"仕分け表_{delivery_date:%Y%m%d}.xlsx"
    export_picking_sheet(tables, out)

    for table in tables:
        names = "・".join(s.display_name for s in table.stores)
        print(f"  {table.group}: {table.item_count}品目 / {len(table.stores)}店舗（{names}）")
    print(f"仕分け表を作成しました（{delivery_date:%Y/%m/%d}）: {out}")
    return 0


def _cmd_input_screen(ctx: AppContext, args) -> int:
    from .web import serve

    serve(ctx, port=args.port, open_browser=not args.no_browser)
    return 0


def _cmd_ledger(ctx: AppContext, args) -> int:
    period = _period_from_month(ctx, args.month)
    orders = ctx.ledger.orders_between(period.start, period.end, args.store)
    if not orders:
        print(f"対象期間（{period.label}）に注文がありません。")
        return 0

    out = ctx.output_dir / f"仕分け帳_{period.end:%Y%m}.xlsx"
    export_sorting_ledger(orders, ctx.stores, ctx.products, out)
    print(f"仕分け帳を出力しました（{period.label} / {len(orders)}件）: {out}")
    return 0


def _cmd_delivery_note(ctx: AppContext, args) -> int:
    delivery_date = _parse_date(args.date)
    orders = ctx.ledger.orders_on(delivery_date, args.store)
    if not orders:
        print(f"{delivery_date:%Y/%m/%d} の注文がありません。")
        return 0

    for store_code in sorted({o.store_code for o in orders}):
        store = ctx.stores.get(store_code)
        rule = store.delivery_note
        if rule is None:
            print(f"[スキップ] {store.display_name}: 納品書テンプレートが未設定です。")
            continue

        note = build_delivery_note(
            store,
            delivery_date,
            orders,
            ctx.products,
            number=f"{delivery_date:%Y%m%d}-{store_code}",
        )
        header, rows = delivery_note_payload(note)
        writer = TemplateWriter(ctx.resolve(rule.template), ctx.layouts[rule.layout])
        out = ctx.output_dir / f"納品書_{delivery_date:%Y%m%d}_{store.display_name}.xlsx"
        writer.render(header, rows, out)
        fee = f" + 送料{note.shipping_fee:,}円" if note.shipping_fee else ""
        print(
            f"納品書を作成しました（{store.display_name} / {len(note.lines)}品目 / "
            f"原価計{note.cost_total:,}円{fee} = {note.total:,}円）: {out}"
        )
    return 0


def _cmd_invoice(ctx: AppContext, args) -> int:
    period = _period_from_month(ctx, args.month)
    orders = ctx.ledger.orders_between(period.start, period.end, args.store)
    if not orders:
        print(f"対象期間（{period.label}）に注文がありません。")
        return 0

    for store_code in sorted({o.store_code for o in orders}):
        store = ctx.stores.get(store_code)
        rule = store.invoice
        if rule is None:
            print(f"[スキップ] {store.display_name}: 請求書テンプレートが未設定です。")
            continue

        invoice = build_invoice(
            store,
            period,
            orders,
            ctx.products,
            issue_date=args.issue_date and _parse_date(args.issue_date) or None,
            payment_due=args.due and _parse_date(args.due) or None,
            number=f"{period.end:%Y%m}-{store_code}",
        )
        header, rows = invoice_payload(invoice)
        writer = TemplateWriter(ctx.resolve(rule.template), ctx.layouts[rule.layout])
        out = ctx.output_dir / f"請求書_{period.end:%Y%m}_{store.display_name}.xlsx"
        writer.render(header, rows, out)

        print(
            f"請求書を作成しました（{store.display_name} / 納品{len(invoice.rows)}行 / "
            f"8%対象{invoice.reduced_total:,}円 + 10%対象{invoice.standard_total:,}円 "
            f"= 税込{invoice.total:,}円（内消費税{round(invoice.tax_total):,}円））: {out}"
        )
    return 0


def _period_from_month(ctx: AppContext, month: str | None):
    if month:
        year, mon = _parse_month(month)
    else:
        today = date.today()
        year, mon = today.year, today.month
    # 締め日は全店舗共通の想定（20日）。店舗ごとに変える場合は stores.yaml で上書き。
    closing_day = next(iter(ctx.stores)).closing_day if len(ctx.stores) else 20
    return closing_period(year, mon, closing_day)


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def _parse_month(text: str) -> tuple[int, int]:
    parsed = datetime.strptime(text, "%Y-%m")
    return parsed.year, parsed.month


def _fmt_qty(qty: float) -> str:
    return str(int(qty)) if float(qty).is_integer() else str(qty)
