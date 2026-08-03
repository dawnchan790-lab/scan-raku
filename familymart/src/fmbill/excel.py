"""現行のExcel帳票をテンプレートとして使い、値だけを流し込む出力エンジン。

テンプレートには現行の数式がそのまま残してある（金額＝数量×単価、合計、消費税など）。
このエンジンが書き込むのは「人が入力していた値」だけで、計算はExcelの数式が行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from .models import DeliveryNote, Invoice


class TemplateOverflowError(Exception):
    """明細がテンプレートの行数に収まらない。"""


@dataclass
class CellSpec:
    ref: str
    format: Optional[str] = None

    @classmethod
    def parse(cls, raw: Any) -> "CellSpec":
        if isinstance(raw, str):
            return cls(ref=raw)
        return cls(ref=raw["ref"], format=raw.get("format"))


@dataclass
class RowSpec:
    start: int
    count: int
    columns: dict[str, str]


@dataclass
class Layout:
    sheet: str
    cells: dict[str, CellSpec]
    rows: RowSpec
    overflow: str = "new_sheet"   # new_sheet | truncate | error

    @classmethod
    def parse(cls, raw: dict) -> "Layout":
        rows = raw.get("rows") or {}
        return cls(
            sheet=raw.get("sheet") or "",
            cells={k: CellSpec.parse(v) for k, v in (raw.get("cells") or {}).items()},
            rows=RowSpec(
                start=int(rows.get("start", 1)),
                count=int(rows.get("count", 0)),
                columns={k: str(v) for k, v in (rows.get("columns") or {}).items()},
            ),
            overflow=raw.get("overflow", "new_sheet"),
        )


def load_layouts(path: str | Path) -> dict[str, Layout]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {name: Layout.parse(raw) for name, raw in data.items()}


class TemplateWriter:
    """テンプレートを開き、レイアウト定義に従って値を書き込む。"""

    def __init__(self, template_path: str | Path, layout: Layout):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            raise FileNotFoundError(
                f"テンプレートが見つかりません: {self.template_path}\n"
                "python3 tools/build_templates.py で現行ブックから生成できます。"
            )
        self.layout = layout

    def render(self, header: dict[str, Any], rows: list[dict[str, Any]], out_path: str | Path):
        workbook = load_workbook(self.template_path)
        base_sheet = (
            workbook[self.layout.sheet] if self.layout.sheet else workbook[workbook.sheetnames[0]]
        )

        per_page = self.layout.rows.count or max(len(rows), 1)
        if len(rows) > per_page and self.layout.overflow == "error":
            raise TemplateOverflowError(
                f"明細が{len(rows)}行あり、テンプレートの{per_page}行に収まりません。\n"
                f"{self.template_path.name} の明細行を増やし、"
                "config/layouts.yaml の rows.count と集計式の範囲を合わせてください。"
            )

        pages = [rows[i : i + per_page] for i in range(0, len(rows), per_page)] or [[]]
        if self.layout.overflow == "truncate":
            pages = pages[:1]

        for index, page_rows in enumerate(pages):
            sheet = base_sheet if index == 0 else workbook.copy_worksheet(base_sheet)
            if index > 0:
                sheet.title = f"{base_sheet.title}_{index + 1}"
            page_header = dict(header)
            page_header["page"] = index + 1
            page_header["page_count"] = len(pages)
            self._write_sheet(sheet, page_header, page_rows, first_row_no=index * per_page + 1)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(out_path)
        return out_path

    def _write_sheet(
        self, sheet: Worksheet, header: dict[str, Any], rows: list[dict[str, Any]], first_row_no: int
    ):
        for key, spec in self.layout.cells.items():
            if key not in header:
                continue
            sheet[spec.ref] = _format_value(header[key], spec.format)

        row_spec = self.layout.rows
        for offset in range(row_spec.count or len(rows)):
            excel_row = row_spec.start + offset
            values = rows[offset] if offset < len(rows) else None
            for key, column in row_spec.columns.items():
                cell = sheet[f"{column}{excel_row}"]
                if values is None:
                    # 未使用の行は空にする。金額欄はテンプレートの数式が空欄を返すので触らない。
                    cell.value = None
                elif key == "line_no":
                    cell.value = first_row_no + offset
                else:
                    cell.value = _format_value(values.get(key), None)


def delivery_note_payload(note: DeliveryNote) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """納品書テンプレートに流し込む値。

    金額（F列・G列）と合計行はテンプレートの数式が計算するので渡さない。
    """
    header = {
        "store_name": note.store.note_addressee,
        "delivery_date": note.delivery_date,
        "number": note.number,
        # 送料行。もらわない店舗は None を書いて空欄にする（数式側が0扱いにする）
        "shipping_label": note.store.delivery_fee.label if note.shipping_fee else None,
        "shipping_cost": note.shipping_fee or None,
    }
    rows = [
        {
            "item_name": ln.item_name,
            "retail_price": ln.retail_price,
            "cost_price": ln.cost_price,
            "qty": _clean_qty(ln.qty),
        }
        for ln in note.lines
    ]
    return header, rows


def invoice_payload(invoice: Invoice) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """請求書テンプレートに流し込む値。

    税率欄・合計・内消費税はテンプレートの数式が計算するので渡さない。
    """
    header = {
        "store_name": f"{invoice.store.name}",
        "issue_date": invoice.issue_date,
        "number": invoice.number,
        "payment_due": invoice.payment_due,
    }
    rows = [
        {
            "sale_date": r.sale_date,
            "item_name": r.item_name,
            # 「※」が入っている行を8%対象として集計式が拾う
            "reduced_mark": "※" if r.reduced_tax else None,
            "qty": r.qty,
            "unit": r.unit or None,
            "amount": r.amount,
        }
        for r in invoice.rows
    ]
    return header, rows


def _format_value(value: Any, fmt: Optional[str]) -> Any:
    if value is None:
        return None
    if fmt and isinstance(value, date):
        return value.strftime(fmt)
    return value


def _clean_qty(qty: float) -> float | int:
    """3.0 のような数量を 3 として書き込む。"""
    return int(qty) if float(qty).is_integer() else qty
