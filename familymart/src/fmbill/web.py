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
