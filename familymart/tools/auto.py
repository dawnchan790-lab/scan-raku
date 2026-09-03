"""帳票をまとめて作る（自動実行用）。

画面を開かずに、その日の仕分け表と納品書、または締め月の請求書を作る。
毎日・毎月の決まった作業を、ダブルクリック1回や定期実行にまとめるためのもの。

    python3 tools/auto.py                    今日の納品ぶん（仕分け表＋納品書）
    python3 tools/auto.py --date 2026-08-05  日付を指定して同じことをする
    python3 tools/auto.py --seikyu           先月の締め分の請求書（全店）
    python3 tools/auto.py --seikyu 2026-08   締め年月を指定して請求書
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fmbill.app import AppContext                      # noqa: E402
from fmbill.billing import build_delivery_note, build_invoice, closing_period  # noqa: E402
from fmbill.excel import (                             # noqa: E402
    TemplateWriter, delivery_note_payload, invoice_payload,
)
from fmbill.picking import build_picking_tables, export_picking_sheet  # noqa: E402


def daily(ctx: AppContext, day: date) -> int:
    """その日の仕分け表と納品書を作る。"""
    orders = ctx.ledger.orders_on(day)
    if not orders:
        print(f"  {day:%Y/%m/%d} の納品数量が入っていません。")
        print("  先に「数量の入力」または「FAXから入れる」で数量を保存してください。")
        return 1

    tables = build_picking_tables(day, orders, ctx.stores, ctx.products)
    out = ctx.output_dir / f"仕分け表_{day:%Y%m%d}.xlsx"
    export_picking_sheet(tables, out)
    print(f"  仕分け表  {out.name}")
    for table in tables:
        print(f"    {table.group}: {table.item_count}品目 / {len(table.stores)}店舗")

    for code in sorted({o.store_code for o in orders}):
        store = ctx.stores.get(code)
        if store.delivery_note is None:
            continue
        note = build_delivery_note(store, day, orders, ctx.products)
        header, rows = delivery_note_payload(note)
        writer = TemplateWriter(
            ctx.resolve(store.delivery_note.template), ctx.layouts[store.delivery_note.layout]
        )
        path = ctx.output_dir / f"納品書_{day:%Y%m%d}_{store.display_name}.xlsx"
        writer.render(header, rows, path)
        fee = f" + 送料{note.shipping_fee:,}円" if note.shipping_fee else ""
        print(f"  納品書    {store.display_name}: 原価{note.cost_total:,}円{fee} = {note.total:,}円")
    return 0


def monthly(ctx: AppContext, year: int, month: int) -> int:
    """締め年月の請求書を全店ぶん作る。"""
    closing_day = next(iter(ctx.stores)).closing_day if len(ctx.stores) else 20
    period = closing_period(year, month, closing_day)
    orders = ctx.ledger.orders_between(period.start, period.end)
    print(f"  対象期間 {period.label}")
    if not orders:
        print("  この期間に納品がありません。")
        return 1

    for code in sorted({o.store_code for o in orders}):
        store = ctx.stores.get(code)
        if store.invoice is None:
            continue
        invoice = build_invoice(
            store, period, orders, ctx.products, number=f"{period.end:%Y%m}-{code}"
        )
        header, rows = invoice_payload(invoice)
        writer = TemplateWriter(
            ctx.resolve(store.invoice.template), ctx.layouts[store.invoice.layout]
        )
        path = ctx.output_dir / f"請求書_{period.end:%Y%m}_{store.display_name}.xlsx"
        writer.render(header, rows, path)
        print(
            f"  請求書    {store.display_name}: 8%対象{invoice.reduced_total:,}円 + "
            f"10%対象{invoice.standard_total:,}円 = 税込{invoice.total:,}円"
        )
    return 0


def main(argv: list[str]) -> int:
    ctx = AppContext()
    print()

    if "--seikyu" in argv:
        index = argv.index("--seikyu")
        given = argv[index + 1] if len(argv) > index + 1 else ""
        if given:
            target = datetime.strptime(given, "%Y-%m")
            year, month = target.year, target.month
        else:
            # 指定がなければ「先月の締め分」。締め日の翌日以降に動かす想定。
            last = date.today().replace(day=1) - timedelta(days=1)
            year, month = last.year, last.month
        print(f"  請求書を作ります（{year}年{month}月締め）")
        result = monthly(ctx, year, month)
    else:
        if "--date" in argv:
            index = argv.index("--date")
            day = datetime.strptime(argv[index + 1], "%Y-%m-%d").date()
        else:
            day = date.today()
        print(f"  仕分け表と納品書を作ります（{day:%Y年%m月%d日} 納品ぶん）")
        result = daily(ctx, day)

    print()
    print(f"  保存先: {ctx.output_dir}")
    print()
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
