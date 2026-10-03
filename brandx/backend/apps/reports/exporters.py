"""
Excel (.xlsx) / CSV exporters.

CSV files are written as UTF-8 with BOM so Excel opens them with correct
Cyrillic / Uzbek characters. Nothing here is Django-specific except the models.
"""
import csv
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

CSV_MIME = 'text/csv; charset=utf-8'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    return value if value is not None else ''


def rows_to_csv(rows):
    """UTF-8 BOM + CRLF so Excel opens it correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    for row in rows:
        writer.writerow([_plain(cell) for cell in row])
    return '\ufeff'.encode('utf-8') + buffer.getvalue().encode('utf-8')


def rows_to_xlsx(rows, title='Report'):
    """First row is treated as the header."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or 'Report'

    for row in rows:
        sheet.append([_plain(cell) for cell in row])

    if rows:
        for col_idx in range(1, len(rows[0]) + 1):
            sheet.cell(row=1, column=col_idx).font = Font(bold=True)
            letter = get_column_letter(col_idx)
            sheet.column_dimensions[letter].width = 18

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
