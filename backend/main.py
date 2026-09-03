import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from pydantic import BaseModel, EmailStr, field_validator


class Lead(BaseModel):
    name: str
    phone: str
    email: EmailStr
    message: str

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value):
        if not isinstance(value, str):
            raise ValueError("Name must be text")
        normalized = " ".join(value.split())
        if not 2 <= len(normalized) <= 100:
            raise ValueError("Name must contain from 2 to 100 characters")
        return normalized

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value):
        if not isinstance(value, str):
            raise ValueError("Phone must be text")
        value = value.strip()
        if not re.fullmatch(r"\+?[\d\s()\-]+", value):
            raise ValueError("Phone contains unsupported characters")
        normalized = re.sub(r"[\s\-()]", "", value)
        digits = normalized.removeprefix("+")
        if not 10 <= len(digits) <= 15:
            raise ValueError("Phone must contain from 10 to 15 digits")
        return normalized

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, value):
        if not isinstance(value, str):
            raise ValueError("Message must be text")
        normalized = value.strip()
        if not 3 <= len(normalized) <= 2000:
            raise ValueError("Message must contain from 3 to 2000 characters")
        return normalized


def normalize_lead(lead: Lead) -> Lead:
    return Lead(
        name=" ".join(lead.name.split()),
        phone=re.sub(r"[\s\-()]", "", lead.phone),
        email=lead.email.strip().lower(),
        message=lead.message.strip(),
    )


project_directory = Path(__file__).resolve().parent.parent
database_path = Path(__file__).resolve().parent / "leads.db"
load_dotenv(project_directory / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def initialize_database():
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new'
            )
            """
        )
        columns = {
            column[1]
            for column in connection.execute("PRAGMA table_info(leads)").fetchall()
        }
        if "telegram_sent" not in columns:
            connection.execute(
                """
                ALTER TABLE leads
                ADD COLUMN telegram_sent INTEGER NOT NULL DEFAULT 0
                """
            )
        if "google_sheets_sent" not in columns:
            connection.execute(
                """
                ALTER TABLE leads
                ADD COLUMN google_sheets_sent INTEGER NOT NULL DEFAULT 0
                """
            )


def send_to_telegram(lead_id: int, lead: Lead) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram is not configured lead_id=%s", lead_id)
        return False

    message = (
        "🔔 Новая заявка\n\n"
        f"Имя: {lead.name}\n"
        f"Телефон: {lead.phone}\n"
        f"Email: {lead.email}\n\n"
        "Сообщение:\n"
        f"{lead.message}\n\n"
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        response.raise_for_status()
        if not response.json().get("ok"):
            raise ValueError("Telegram returned an unsuccessful response")
    except Exception as error:
        logger.error(
            "Telegram sending failed lead_id=%s error_type=%s",
            lead_id,
            type(error).__name__,
        )
        return False

    logger.info("Telegram message sent lead_id=%s", lead_id)
    return True


def send_to_google_sheets(lead_data: dict) -> bool:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    sheet_name = os.getenv("GOOGLE_SHEETS_SHEET_NAME", "Лист1")
    credentials_setting = os.getenv(
        "GOOGLE_SHEETS_CREDENTIALS_FILE",
        "google-service-account.json",
    )
    credentials_path = Path(credentials_setting)
    if not credentials_path.is_absolute():
        credentials_path = project_directory / credentials_path

    if not spreadsheet_id or not credentials_path.is_file():
        logger.warning(
            "Google Sheets is not configured lead_id=%s",
            lead_data["id"],
        )
        return False

    row = [[
        lead_data["id"],
        lead_data["created_at"],
        lead_data["name"],
        lead_data["phone"],
        lead_data["email"],
        lead_data["message"],
        lead_data["status"],
    ]]
    values_range = quote(f"{sheet_name}!A:G", safe="")
    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        f"{spreadsheet_id}/values/{values_range}:append"
    )

    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        credentials.refresh(Request())
        response = httpx.post(
            url,
            params={
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
            },
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={"values": row},
            timeout=10,
        )
        response.raise_for_status()
        if response.json().get("updates", {}).get("updatedRows", 0) < 1:
            raise ValueError("Google Sheets did not append a row")
    except Exception as error:
        logger.error(
            "Google Sheets saving failed lead_id=%s error_type=%s",
            lead_data["id"],
            type(error).__name__,
        )
        return False

    logger.info("Google Sheets row saved lead_id=%s", lead_data["id"])
    return True


initialize_database()


app = FastAPI(title="LeadFlow API")


@app.get("/health")
def health():
    try:
        with sqlite3.connect(database_path) as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        logger.error(
            "Database health check failed error_type=%s",
            type(error).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )

    return {"status": "ok", "database": "ok"}


@app.post("/api/leads")
def create_lead(lead: Lead):
    lead = normalize_lead(lead)

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            """
            SELECT id
            FROM leads
            WHERE name = ?
              AND phone = ?
              AND email = ?
              AND message = ?
              AND created_at >= datetime('now', '-5 minutes')
            ORDER BY id DESC
            LIMIT 1
            """,
            (lead.name, lead.phone, lead.email, lead.message),
        ).fetchone()

        if duplicate:
            return {
                "success": True,
                "duplicate": True,
                "message": "Заявка уже была принята",
            }

        cursor = connection.execute(
            """
            INSERT INTO leads (name, phone, email, message)
            VALUES (?, ?, ?, ?)
            """,
            (lead.name, lead.phone, lead.email, lead.message),
        )
        lead_id = cursor.lastrowid
        row = connection.execute(
            """
            SELECT id, created_at, name, phone, email, message, status
            FROM leads
            WHERE id = ?
            """,
            (lead_id,),
        ).fetchone()

    lead_data = {
        "id": row[0],
        "created_at": row[1],
        "name": row[2],
        "phone": row[3],
        "email": row[4],
        "message": row[5],
        "status": row[6],
    }

    telegram_sent = send_to_telegram(lead_id, lead)
    if telegram_sent:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE leads SET telegram_sent = 1 WHERE id = ?",
                (lead_id,),
            )

    google_sheets_sent = send_to_google_sheets(lead_data)
    if google_sheets_sent:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE leads SET google_sheets_sent = 1 WHERE id = ?",
                (lead_id,),
            )

    return {
        "success": True,
        "duplicate": False,
        "message": "Заявка принята",
    }


@app.get("/", include_in_schema=False)
def get_site():
    return FileResponse(project_directory / "index.html")


@app.get("/styles.css", include_in_schema=False)
def get_styles():
    return FileResponse(project_directory / "styles.css", media_type="text/css")


@app.get("/script.js", include_in_schema=False)
def get_script():
    return FileResponse(project_directory / "script.js", media_type="text/javascript")
