"""仕分け帳。取り込んだ注文を店舗×納品日に仕分けて保存する。

保存先は SQLite 1ファイル。Excelで開いていてもロックされず、
同じ注文を二重に取り込んでも検知できるようにしている。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from .models import Order, OrderLine

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    store_code    TEXT NOT NULL,
    delivery_date TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT '',
    source_ref    TEXT NOT NULL DEFAULT '',
    received_at   TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS order_lines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_code TEXT NOT NULL DEFAULT '',
    item_name    TEXT NOT NULL,
    qty          REAL NOT NULL,
    input_qty    REAL NOT NULL DEFAULT 0,
    unit         TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    raw_text     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_orders_store_date ON orders(store_code, delivery_date);
"""


class Ledger:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def add_orders(self, orders: Iterable[Order], skip_duplicates: bool = True) -> list[Order]:
        """注文を保存し、実際に保存されたものを返す。

        同じ店舗・同じ納品日・同じ取込元（source_ref）の注文が既にある場合は
        二重取り込みとみなして既定でスキップする。
        """
        saved: list[Order] = []
        with closing(self._connect()) as conn:
            for order in orders:
                if skip_duplicates and order.source_ref and self._exists(conn, order):
                    continue
                cursor = conn.execute(
                    "INSERT INTO orders (store_code, delivery_date, source, source_ref,"
                    " received_at, note) VALUES (?,?,?,?,?,?)",
                    (
                        order.store_code,
                        order.delivery_date.isoformat(),
                        order.source,
                        order.source_ref,
                        order.received_at.isoformat() if order.received_at else "",
                        order.note,
                    ),
                )
                order.order_id = cursor.lastrowid
                conn.executemany(
                    "INSERT INTO order_lines (order_id, product_code, item_name, qty,"
                    " input_qty, unit, note, raw_text) VALUES (?,?,?,?,?,?,?,?)",
                    [
                        (
                            order.order_id,
                            ln.product_code,
                            ln.item_name,
                            ln.qty,
                            ln.input_qty,
                            ln.unit,
                            ln.note,
                            ln.raw_text,
                        )
                        for ln in order.lines
                    ],
                )
                saved.append(order)
            conn.commit()
        return saved

    def orders_between(
        self, start: date, end: date, store_code: Optional[str] = None
    ) -> list[Order]:
        """納品日が start〜end（両端を含む）の注文を取り出す。"""
        sql = (
            "SELECT * FROM orders WHERE delivery_date BETWEEN ? AND ?"
            + (" AND store_code = ?" if store_code else "")
            + " ORDER BY delivery_date, store_code, id"
        )
        params: list = [start.isoformat(), end.isoformat()]
        if store_code:
            params.append(store_code)

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                return []
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(ids))
            line_rows = conn.execute(
                f"SELECT * FROM order_lines WHERE order_id IN ({placeholders}) ORDER BY id",
                ids,
            ).fetchall()

        lines_by_order: dict[int, list[OrderLine]] = {}
        for row in line_rows:
            lines_by_order.setdefault(row["order_id"], []).append(
                OrderLine(
                    raw_text=row["raw_text"],
                    item_name=row["item_name"],
                    qty=row["qty"],
                    input_qty=row["input_qty"],
                    unit=row["unit"],
                    product_code=row["product_code"],
                    note=row["note"],
                )
            )

        return [
            Order(
                store_code=row["store_code"],
                delivery_date=date.fromisoformat(row["delivery_date"]),
                lines=lines_by_order.get(row["id"], []),
                source=row["source"],
                source_ref=row["source_ref"],
                received_at=date.fromisoformat(row["received_at"]) if row["received_at"] else None,
                note=row["note"],
                order_id=row["id"],
            )
            for row in rows
        ]

    def orders_on(self, delivery_date: date, store_code: Optional[str] = None) -> list[Order]:
        return self.orders_between(delivery_date, delivery_date, store_code)

    def _exists(self, conn: sqlite3.Connection, order: Order) -> bool:
        row = conn.execute(
            "SELECT 1 FROM orders WHERE store_code=? AND delivery_date=? AND source_ref=? LIMIT 1",
            (order.store_code, order.delivery_date.isoformat(), order.source_ref),
        ).fetchone()
        return row is not None
