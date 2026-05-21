import os
import subprocess
import sys
from pathlib import Path

import requests
import streamlit as st

# Địa chỉ backend FastAPI
_API_URL = "http://127.0.0.1:8080/api/v1/chat"

# Thư mục lưu tài liệu và script ingest
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCS_DATA_DIR = _PROJECT_ROOT / "docs" / "data"
_INGEST_SCRIPT = _PROJECT_ROOT / "src" / "retrieval" / "ingest.py"

# Định dạng file được chấp nhận
_ACCEPTED_TYPES = ["txt", "pdf", "docx", "csv", "xlsx", "xls"]

# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(page_title="LangGraph AI Agent", page_icon="🤖", layout="centered")
st.title("🤖 LangGraph AI Agent")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Thông tin")
    st.markdown(
        "Chatbot được xây dựng với **FastAPI + LangGraph + ChromaDB**.\n\n"
        "Mỗi `Thread ID` là một phiên hội thoại độc lập — "
        "thay đổi ID để bắt đầu cuộc trò chuyện mới."
    )
    st.divider()

    # ── Thread ID ────────────────────────────────────────────────────────────
    thread_id = st.text_input(
        "Thread ID",
        value="session-001",
        help="Dùng để định danh phiên và lưu trí nhớ hội thoại.",
    )
    st.divider()

    # ── Upload tài liệu ──────────────────────────────────────────────────────
    st.subheader("📂 Tải lên tài liệu")
    st.caption("Hỗ trợ: TXT, PDF, DOCX, CSV, XLSX, XLS")

    uploaded_files = st.file_uploader(
        "Chọn file",
        type=_ACCEPTED_TYPES,
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if st.button("⚡ Nạp vào Knowledge Base", use_container_width=True):
        if not uploaded_files:
            st.warning("Vui lòng chọn ít nhất một file.")
        else:
            # Lưu từng file vào docs/data/
            _DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
            saved = []
            for f in uploaded_files:
                dest = _DOCS_DATA_DIR / f.name
                dest.write_bytes(f.read())
                saved.append(f.name)

            st.info(f"Đã lưu {len(saved)} file: {', '.join(saved)}")

            # Chạy ingest.py để nạp vào ChromaDB
            with st.spinner("Đang xử lý và nạp vào ChromaDB..."):
                result = subprocess.run(
                    [sys.executable, str(_INGEST_SCRIPT)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )

            if result.returncode == 0:
                # Lấy dòng cuối của stdout làm thông báo thành công
                output = result.stdout.strip().splitlines()
                st.success(output[-1] if output else "Nạp thành công!")
            else:
                st.error(f"Lỗi khi nạp:\n```\n{result.stderr[-500:]}\n```")

# ── Khởi tạo lịch sử tin nhắn trong session state ────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Hiển thị toàn bộ lịch sử hội thoại ──────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ── Ô nhập liệu ──────────────────────────────────────────────────────────────
if prompt := st.chat_input("Nhập câu hỏi của bạn..."):
    # Hiển thị tin nhắn người dùng ngay lập tức
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Gọi backend và hiển thị phản hồi
    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            try:
                response = requests.post(
                    _API_URL,
                    json={"query": prompt, "thread_id": thread_id},
                    timeout=60,
                )
                response.raise_for_status()
                answer = response.json()["answer"]
            except requests.exceptions.ConnectionError:
                answer = (
                    "⚠️ Không kết nối được backend. "
                    "Hãy chắc chắn server đang chạy tại `http://127.0.0.1:8080`."
                )
            except requests.exceptions.Timeout:
                answer = "⚠️ Backend mất quá nhiều thời gian phản hồi (>60s). Thử lại sau."
            except Exception as e:
                answer = f"⚠️ Lỗi không xác định: {e}"

        st.write(answer)

    # Lưu phản hồi vào lịch sử
    st.session_state.messages.append({"role": "assistant", "content": answer})
