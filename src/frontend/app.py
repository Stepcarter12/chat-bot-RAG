from pathlib import Path

import requests
import streamlit as st

# Địa chỉ backend FastAPI
_API_URL = "http://127.0.0.1:8080/api/v1/chat"
_FILES_API_BASE = "http://127.0.0.1:8080/api/v1/files"
_INGEST_API = "http://127.0.0.1:8080/api/v1/ingest"

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCS_DATA_DIR = _PROJECT_ROOT / "docs" / "data"

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

    # ── Chọn mô hình nhúng ───────────────────────────────────────────────────
    st.subheader("🌐 Ngôn ngữ tài liệu (Embedding Model)")
    _EMBEDDING_OPTIONS = {
        "Tiếng Anh (all-MiniLM-L6-v2)": "en",
        "Tiếng Việt (multilingual-e5-small)": "vi",
    }
    embedding_label = st.selectbox(
        "Chọn ngôn ngữ tài liệu",
        options=list(_EMBEDDING_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
        help="Chọn mô hình nhúng phù hợp với ngôn ngữ tài liệu trong Knowledge Base.",
    )
    embedding_type = _EMBEDDING_OPTIONS[embedding_label]
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
            # Bước 1: Upload từng file lên backend qua API
            saved = []
            upload_ok = True
            for f in uploaded_files:
                try:
                    r = requests.post(
                        _FILES_API_BASE,
                        files={"file": (f.name, f.getvalue())},
                        timeout=30,
                    )
                    r.raise_for_status()
                    saved.append(f.name)
                except requests.exceptions.ConnectionError:
                    st.error("Không kết nối được backend. Hãy chắc chắn server đang chạy.")
                    upload_ok = False
                    break
                except Exception as e:
                    st.error(f"Lỗi khi lưu '{f.name}': {e}")
                    upload_ok = False
                    break

            if upload_ok and saved:
                st.info(f"Đã lưu {len(saved)} file: {', '.join(saved)}")

                # Bước 2: Gọi API ingest với đúng embedding_type người dùng đang chọn
                with st.spinner("Đang xử lý và nạp vào ChromaDB..."):
                    try:
                        resp = requests.post(
                            _INGEST_API,
                            json={"chunk_size": 500, "chunk_overlap": 50, "embedding_type": embedding_type},
                            timeout=120,
                        )
                        resp.raise_for_status()
                        total = resp.json().get("total", 0)
                        st.success(f"Đã nạp thành công {total} chunks ({embedding_label})!")
                    except requests.exceptions.ConnectionError:
                        st.error("Không kết nối được backend.")
                    except requests.exceptions.Timeout:
                        st.error("Backend mất quá nhiều thời gian (>120s). Thử lại sau.")
                    except Exception as e:
                        st.error(f"Lỗi khi nạp: {e}")

    st.divider()

    # ── Quản lý Cơ sở dữ liệu RAG ────────────────────────────────────────────
    with st.expander("⚙️ Quản lý Cơ sở dữ liệu"):
        st.caption("Tùy chỉnh thông số chunking và xem trước kết quả cắt văn bản.")
        chunk_size = st.number_input(
            "Chunk Size",
            min_value=100,
            max_value=3000,
            value=500,
            step=50,
            help="Số ký tự tối đa trong mỗi chunk.",
        )
        chunk_overlap = st.number_input(
            "Chunk Overlap",
            min_value=0,
            max_value=500,
            value=50,
            step=10,
            help="Số ký tự chồng lấp giữa các chunk liền kề.",
        )

        if st.button("🔄 Cập nhật Database & Xem trước Chunks", use_container_width=True):
            with st.spinner("Đang nạp lại và cắt tài liệu..."):
                try:
                    resp = requests.post(
                        "http://127.0.0.1:8080/api/v1/ingest",
                        json={
                            "chunk_size": int(chunk_size),
                            "chunk_overlap": int(chunk_overlap),
                            "embedding_type": embedding_type,
                        },
                        timeout=120,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    chunks_preview = data["chunks"]
                    st.success(f"Đã nạp thành công {data['total']} chunks!")
                    for i, chunk_text in enumerate(chunks_preview, 1):
                        with st.expander(f"Chunk {i} ({len(chunk_text)} ký tự)"):
                            st.info(chunk_text)
                except requests.exceptions.ConnectionError:
                    st.error(
                        "Không kết nối được backend. "
                        "Hãy chắc chắn server đang chạy tại `http://127.0.0.1:8080`."
                    )
                except requests.exceptions.Timeout:
                    st.error("Backend mất quá nhiều thời gian phản hồi (>120s). Thử lại sau.")
                except Exception as e:
                    st.error(f"Lỗi không xác định: {e}")

    st.divider()

    # ── Quản lý File Tài Liệu ─────────────────────────────────────────────────
    with st.expander("📁 Quản lý File Tài Liệu"):
        # Upload file mới tự động khi chọn (chỉ .txt và .md)
        new_file = st.file_uploader(
            "Tải lên file mới (.txt, .md)",
            type=["txt", "md"],
            key="doc_mgmt_uploader",
        )
        if new_file is not None:
            # Dùng session_state để tránh gọi API lại khi Streamlit re-render
            if st.session_state.get("_uploaded_doc") != new_file.name:
                try:
                    resp = requests.post(
                        _FILES_API_BASE,
                        files={"file": (new_file.name, new_file.getvalue())},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    st.success(f"Đã tải lên: {new_file.name}")
                    st.session_state["_uploaded_doc"] = new_file.name
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("Không kết nối được backend.")
                except Exception as e:
                    st.error(f"Lỗi tải lên: {e}")

        # Danh sách file hiện có + nút xóa
        st.markdown("**Danh sách file trong `docs/data/`:**")
        try:
            r = requests.get(_FILES_API_BASE, timeout=10)
            r.raise_for_status()
            file_list = r.json().get("files", [])
            if not file_list:
                st.caption("Chưa có file nào.")
            else:
                for fname in file_list:
                    col1, col2 = st.columns([4, 1])
                    col1.text(fname)
                    if col2.button("🗑️", key=f"del_{fname}", help=f"Xóa {fname}"):
                        try:
                            dr = requests.delete(f"{_FILES_API_BASE}/{fname}", timeout=10)
                            dr.raise_for_status()
                            st.success(f"Đã xóa: {fname}")
                            st.rerun()
                        except requests.exceptions.ConnectionError:
                            st.error("Không kết nối được backend.")
                        except Exception as e:
                            st.error(f"Lỗi xóa: {e}")
        except requests.exceptions.ConnectionError:
            st.error("Không kết nối được backend. Hãy chắc chắn server đang chạy.")
        except Exception as e:
            st.error(f"Lỗi tải danh sách: {e}")

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
                    json={"query": prompt, "thread_id": thread_id, "embedding_type": embedding_type},
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
