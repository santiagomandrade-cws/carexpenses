import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
GROUP_JID = os.getenv("GROUP_JID", "")
PORT = int(os.getenv("PORT", "8000"))
