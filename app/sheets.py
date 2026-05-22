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
