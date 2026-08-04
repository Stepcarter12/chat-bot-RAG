"""
Lead capture service — lưu thông tin khách hàng tiềm năng vào Google Sheets.
Được gọi từ Celery worker sau khi phát hiện SĐT trong tin nhắn khách.
"""
import os
import re
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from src.core.utils import get_logger

_logger = get_logger(__name__)

_PHONE_PATTERN = re.compile(r"(?<!\d)(0[3-9]\d{8}|\+84[3-9]\d{8})(?!\d)")

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADERS = ["STT", "Thời gian", "PSID", "Tên sản phẩm", "Số điện thoại", "Tin nhắn"]

# Singleton — khởi tạo 1 lần, tái dùng cho mọi lần gọi
_sheet_instance: gspread.Worksheet | None = None


def _get_sheet() -> gspread.Worksheet:
    global _sheet_instance
    if _sheet_instance is None:
        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/google_credentials.json")
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        creds = Credentials.from_service_account_file(creds_path, scopes=_SCOPES)
        client = gspread.authorize(creds)
        _sheet_instance = client.open_by_key(sheet_id).sheet1
        _logger.info("Đã kết nối Google Sheet (singleton)")
    return _sheet_instance


def init_leads_table() -> None:
    """Tạo header row nếu sheet còn trống."""
    try:
        sheet = _get_sheet()
        if not sheet.get_all_values():
            sheet.append_row(_HEADERS)
            _logger.info("Đã tạo header row trong Google Sheet")
        else:
            _logger.debug("Google Sheet đã có dữ liệu, bỏ qua init")
    except Exception as e:
        _logger.warning("Không thể khởi tạo Google Sheet: %s", e)


def save_lead_if_new(psid: str, thread_id: str, message_text: str, product: str = "") -> bool:
    """
    Nếu message_text chứa SĐT và chưa có lead với psid+phone này → lưu vào Sheet.
    Trả về True nếu lead mới được lưu, False nếu bỏ qua (trùng hoặc không có SĐT).
    """
    match = _PHONE_PATTERN.search(message_text)
    if not match:
        return False

    phone = match.group(1)

    try:
        sheet = _get_sheet()
        rows = sheet.get_all_values()

        # Kiểm tra trùng: cột PSID (index 2) và phone (index 4)
        for row in rows[1:]:  # bỏ header
            if len(row) >= 5 and row[2] == psid and row[4] == phone:
                return False

        stt = len(rows)  # số thứ tự (không tính header)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([stt, now, psid, product, phone, message_text])
        _logger.info("Lead mới: PSID=%s, phone=%s, product=%s", psid, phone, product)
        return True

    except Exception as exc:
        _logger.error("Lỗi khi lưu lead PSID=%s: %s", psid, exc)
        return False


def get_all_leads() -> list[dict]:
    """Đọc toàn bộ lead từ Google Sheet, trả về list dict."""
    try:
        sheet = _get_sheet()
        rows = sheet.get_all_values()
        if len(rows) <= 1:
            return []
        leads = []
        for row in rows[1:]:  # bỏ header
            if len(row) >= 5:
                leads.append({
                    "id": row[0],
                    "created_at": row[1],
                    "psid": row[2],
                    "product": row[3] if len(row) > 3 else "",
                    "phone": row[4],
                    "raw_message": row[5] if len(row) > 5 else "",
                })
        return list(reversed(leads))  # mới nhất lên đầu
    except Exception as exc:
        _logger.error("Lỗi khi đọc leads từ Google Sheet: %s", exc)
        return []
