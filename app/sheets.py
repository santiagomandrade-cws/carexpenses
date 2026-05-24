from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from app.config import GOOGLE_CREDENTIALS_FILE, SPREADSHEET_ID
from app.parser import Expense

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_HEADERS = ["Data", "Hora", "Descrição", "Valor (R$)", "Mensagem original"]


def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=_SCOPES)
    return gspread.authorize(creds)


def get_sheet() -> gspread.Worksheet:
    sheet = _client().open_by_key(SPREADSHEET_ID).sheet1
    if not sheet.get_all_values():
        sheet.append_row(_HEADERS)
    return sheet


def append_expense(expense: Expense) -> None:
    sheet = get_sheet()
    sheet.append_row([
        expense.date,
        expense.time,
        expense.description,
        expense.value,
        expense.raw_message,
    ])


def get_monthly_summary(year: int, month: int) -> dict:
    sheet = get_sheet()
    rows = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    expenses = []
    for row in rows:
        try:
            d = datetime.strptime(row.get("Data", ""), "%d/%m/%Y")
            if d.year == year and d.month == month:
                expenses.append(row)
        except ValueError:
            continue
    total = sum(float(row.get("Valor (R$)", 0) or 0) for row in expenses)
    return {"total": total, "count": len(expenses), "expenses": expenses}
