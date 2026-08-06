"""納品数量の入力画面（PC用）。

売り場の画像を見て決めた「何を何個入れるか」を入力するための画面。
ブラウザで開いて店舗と納品日を選び、品目ごとに数量を打ち込んで保存する。

    python3 -m fmbill nyuryoku

外部ライブラリは使わず、Python標準のHTTPサーバで動く。
自分のパソコンの中だけで動き、外からはつながらない（127.0.0.1で待ち受ける）。
"""

from __future__ import annotations

import base64
import io
import json
import tempfile
import threading
import webbrowser
from datetime import date, datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app import AppContext
from .billing import build_delivery_note
from .models import Order, OrderLine

STATIC_DIR = Path(__file__).resolve().parent / "static"


class InputHandler(BaseHTTPRequestHandler):
    """入力画面のリクエストを処理する。"""

    def __init__(self, *args, ctx: AppContext, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if route.path in ("/", "/index.html"):
            return self._send_file(STATIC_DIR / "nyuryoku.html", "text/html; charset=utf-8")
        if route.path == "/api/stores":
            return self._send_json({"stores": self._stores()})
        if route.path == "/api/products":
            return self._send_json(self._products(query.get("store", [""])[0]))
        if route.path == "/api/order":
            return self._send_json(
                self._existing_order(query.get("store", [""])[0], query.get("date", [""])[0])
            )
        if route.path == "/fax":
            return self._send_file(STATIC_DIR / "fax.html", "text/html; charset=utf-8")
        if route.path == "/kakaku":
            return self._send_file(STATIC_DIR / "kakaku.html", "text/html; charset=utf-8")
        if route.path == "/shorui":
            return self._send_file(STATIC_DIR / "shorui.html", "text/html; charset=utf-8")
        if route.path == "/favicon.ico":
            # ブラウザが必ず取りに来る。用意していないので「中身なし」で静かに返す
            self.send_response(204)
            self.end_headers()
            return
        self._send_json({"error": "not found"}, status=404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        route = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if route.path == "/api/order":
                body = json.loads(self.rfile.read(length) or b"{}")
                return self._send_json(self._save(body))
            if route.path == "/api/fax":
                name = parse_qs(route.query).get("name", ["fax.pdf"])[0]
                return self._send_json(self._read_fax(self.rfile.read(length), name))
            if route.path == "/api/prices":
                body = json.loads(self.rfile.read(length) or b"{}")
                return self._send_json(self._save_prices(body))
            if route.path == "/api/documents":
                body = json.loads(self.rfile.read(length) or b"{}")
                return self._send_json(self._make_documents(body))
            self._send_json({"error": "not found"}, status=404)
        except Exception as error:  # 画面側で原因が見えるように本文で返す
            self._send_json({"error": str(error)}, status=400)

    def _read_fax(self, blob: bytes, filename: str) -> dict:
        """FAXの画像・PDFを行ごとに切り分けて、確認用の画像を返す。

        数字の読み取りまでは行わない。切り出した画像を画面に並べ、
        人が目で見て数量を入れる（読み違いによる誤請求を避けるため）。
        """
        from .faxreader import read_file

        suffix = Path(filename).suffix.lower() or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(blob)
            tmp.flush()
            sheets = read_file(tmp.name, dpi=150)

        if not sheets:
            return {"error": "表を読み取れませんでした。傾きの少ない、明るい画像でお試しください。"}

        pages = []
        for sheet in sheets:
            pages.append(
                {
                    "page": sheet.page,
                    "header": _to_data_url(sheet.header, height=220),
                    "rows": [
                        {
                            "index": cell.row_index,
                            "name": _to_data_url(cell.name_image, height=44),
                            "qty": _to_data_url(cell.image, height=44),
                            "ink": round(cell.ink_ratio, 4),
                        }
                        for cell in sheet.cells
                    ],
                }
            )
        return {"pages": pages}

    def _make_documents(self, body: dict) -> dict:
        """画面のボタンから帳票を作る。コマンドを打たずにテスト運用できるようにする。"""
        kind = body.get("kind")
        if kind == "shiwakehyo":
            return self._make_picking(_parse_date(body["date"]))
        if kind == "nouhin":
            return self._make_notes(_parse_date(body["date"]))
        if kind == "seikyu":
            return self._make_invoices(body["month"])
        raise ValueError(f"知らない帳票です: {kind}")

    def _make_picking(self, delivery_date: date) -> dict:
        from .picking import build_picking_tables, export_picking_sheet

        orders = self.ctx.ledger.orders_on(delivery_date)
        if not orders:
            return {"messages": [f"{delivery_date:%Y/%m/%d} の納品数量がありません。"], "files": []}

        tables = build_picking_tables(delivery_date, orders, self.ctx.stores, self.ctx.products)
        out = self.ctx.output_dir / f"仕分け表_{delivery_date:%Y%m%d}.xlsx"
        export_picking_sheet(tables, out)
        return {
            "messages": [
                f"{t.group}: {t.item_count}品目 / {len(t.stores)}店舗" for t in tables
            ],
            "files": [str(out)],
        }

    def _make_notes(self, delivery_date: date) -> dict:
        from .billing import build_delivery_note
        from .excel import TemplateWriter, delivery_note_payload

        orders = self.ctx.ledger.orders_on(delivery_date)
        if not orders:
            return {"messages": [f"{delivery_date:%Y/%m/%d} の納品数量がありません。"], "files": []}

        messages, files = [], []
        for store_code in sorted({o.store_code for o in orders}):
            store = self.ctx.stores.get(store_code)
            if store.delivery_note is None:
                messages.append(f"{store.display_name}: 納品書の設定がありません。")
                continue
            note = build_delivery_note(store, delivery_date, orders, self.ctx.products)
            header, rows = delivery_note_payload(note)
            writer = TemplateWriter(
                self.ctx.resolve(store.delivery_note.template),
                self.ctx.layouts[store.delivery_note.layout],
            )
            out = (
                self.ctx.output_dir
                / f"納品書_{delivery_date:%Y%m%d}_{store.display_name}.xlsx"
            )
            writer.render(header, rows, out)
            fee = f" + 送料{note.shipping_fee:,}円" if note.shipping_fee else ""
            messages.append(
                f"{store.display_name}: {len(note.lines)}品目 "
                f"原価{note.cost_total:,}円{fee} = {note.total:,}円"
            )
            files.append(str(out))
        return {"messages": messages, "files": files}

    def _make_invoices(self, month: str) -> dict:
        from .billing import build_invoice, closing_period
        from .excel import TemplateWriter, invoice_payload

        year, mon = int(month[:4]), int(month[5:7])
        closing_day = next(iter(self.ctx.stores)).closing_day if len(self.ctx.stores) else 20
        period = closing_period(year, mon, closing_day)
        orders = self.ctx.ledger.orders_between(period.start, period.end)
        if not orders:
            return {"messages": [f"{period.label} に納品がありません。"], "files": []}

        messages, files = [], []
        for store_code in sorted({o.store_code for o in orders}):
            store = self.ctx.stores.get(store_code)
            if store.invoice is None:
                continue
            invoice = build_invoice(
                store, period, orders, self.ctx.products,
                number=f"{period.end:%Y%m}-{store_code}",
            )
            header, rows = invoice_payload(invoice)
            writer = TemplateWriter(
                self.ctx.resolve(store.invoice.template),
                self.ctx.layouts[store.invoice.layout],
            )
            out = self.ctx.output_dir / f"請求書_{period.end:%Y%m}_{store.display_name}.xlsx"
            writer.render(header, rows, out)
            messages.append(
                f"{store.display_name}: 8%対象{invoice.reduced_total:,}円 + "
                f"10%対象{invoice.standard_total:,}円 = 税込{invoice.total:,}円"
            )
            files.append(str(out))
        return {"messages": [f"対象期間 {period.label}"] + messages, "files": files}

    def _save_prices(self, body: dict) -> dict:
        """売価の変更を商品マスタに書き戻す。原価は掛け率から計算し直される。"""
        from .pricebook import update_prices

        prices = {str(k): int(v) for k, v in (body.get("prices") or {}).items()}
        changed = update_prices(self.ctx.config_dir / "products.yaml", prices)
        # 次に読むときに新しい売価が効くよう、読み込み済みのマスタを捨てる
        self.ctx.__dict__.pop("products", None)
        return {"changed": changed}

    # ------------------------------------------------------------- handlers
    def _stores(self) -> list[dict]:
        return [
            {
                "code": store.code,
                "name": store.name,
                "short_name": store.display_name,
                "group": store.group,
                "margin_rate": store.margin_rate,
                "order_unit": store.order_unit,
                "shipping": store.delivery_fee.amount if store.delivery_fee.enabled else 0,
            }
            for store in self.ctx.stores
        ]

    def _products(self, store_code: str) -> dict:
        if not store_code:
            return {"products": []}
        store = self.ctx.stores.get(store_code)
        products = [
            {
                "code": product.code,
                "name": product.name,
                "spec": product.spec,
                "unit": product.unit,
                "retail_price": product.retail_price_for(store),
                "cost_price": product.cost_price_for(store),
                "margin_rate": product.margin_rate_for(store),
                "min_lot": product.min_lot,
                "reduced_tax": product.reduced_tax,
            }
            for product in self.ctx.products
            if product.applies_to(store)
        ]
        return {
            "store": {
                "code": store.code,
                "name": store.name,
                "order_unit": store.order_unit,
                "shipping": store.delivery_fee.amount if store.delivery_fee.enabled else 0,
            },
            "products": products,
        }

    def _existing_order(self, store_code: str, day: str) -> dict:
        """保存済みの数量を返す。開き直して直せるようにするため。"""
        if not store_code or not day:
            return {"quantities": {}}
        orders = self.ctx.ledger.orders_on(_parse_date(day), store_code)
        quantities: dict[str, float] = {}
        for order in orders:
            for line in order.lines:
                if line.product_code:
                    quantities[line.product_code] = quantities.get(line.product_code, 0) + (
                        line.input_qty or line.qty
                    )
        return {"quantities": quantities}

    def _save(self, body: dict) -> dict:
        store = self.ctx.stores.get(body["store"])
        delivery_date = _parse_date(body["date"])
        entries = {k: float(v) for k, v in (body.get("quantities") or {}).items() if float(v) > 0}

        lines = []
        for code, number in entries.items():
            product = self.ctx.products.get(code)
            qty = number * product.min_lot if store.order_unit == "lot" else number
            lines.append(
                OrderLine(
                    raw_text=f"入力画面 {product.name} {number}",
                    item_name=product.name,
                    qty=qty,
                    input_qty=number,
                    unit=product.unit,
                    product_code=product.code,
                )
            )

        order = Order(
            store_code=store.code,
            delivery_date=delivery_date,
            lines=lines,
            source="manual",
            source_ref="入力画面",
            received_at=date.today(),
        )
        self.ctx.ledger.replace_order(order)

        note = build_delivery_note(store, delivery_date, [order], self.ctx.products)
        return {
            "saved": len(lines),
            "cost_total": note.cost_total,
            "shipping": note.shipping_fee,
            "total": note.total,
        }

    # --------------------------------------------------------------- helpers
    def _send_json(self, payload: dict, status: int = 200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            return self._send_json({"error": f"見つかりません: {path.name}"}, status=404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass    # アクセスログは出さない


def serve(ctx: AppContext, port: int = 8765, open_browser: bool = True) -> None:
    handler = partial(InputHandler, ctx=ctx)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"

    print(f"入力画面を開きました: {url}")
    print("終了するには Ctrl+C を押してください。")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
    finally:
        server.server_close()


def _to_data_url(image, height: int) -> str:
    """画面に埋め込めるようPNGにしてbase64にする。高さをそろえて読みやすくする。"""
    if image is None:
        return ""
    if image.height > height:
        ratio = height / image.height
        image = image.resize((max(1, int(image.width * ratio)), height))
    buffer = io.BytesIO()
    image.convert("L").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _parse_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()
