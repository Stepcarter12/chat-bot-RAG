import io
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# Đọc base URL từ env: trong Docker dùng service name, local dùng localhost
# Backward-compatible: nếu không có env var, mặc định về localhost
_API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

_API_URL = f"{_API_BASE}/api/v1/chat"
_FILES_API_BASE = f"{_API_BASE}/api/v1/files"
_INGEST_API = f"{_API_BASE}/api/v1/ingest"

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCS_DATA_DIR = _PROJECT_ROOT / "docs" / "data"

# Định dạng file được chấp nhận
_ACCEPTED_TYPES = ["txt", "pdf", "docx", "csv", "xlsx", "xls"]

_LEADS_API = f"{_API_BASE}/api/v1/leads"


def _leads_page() -> None:
    """Trang xem danh sách lead thu thập từ Messenger."""
    st.header("📋 Danh sách Lead")

    if st.button("🔄 Tải lại"):
        st.rerun()

    try:
        resp = requests.get(_LEADS_API, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Không kết nối được backend.")
        return
    except Exception as e:
        st.error(f"Lỗi: {e}")
        return

    leads = data.get("leads", [])
    if not leads:
        st.info("Chưa có lead nào được thu thập.")
        return

    st.metric("Tổng số lead", len(leads))
    st.divider()

    df = pd.DataFrame(leads)[["id", "created_at", "psid", "product", "phone", "raw_message"]]
    df.columns = ["STT", "Thời gian", "PSID (Facebook)", "Sản phẩm quan tâm", "Số điện thoại", "Tin nhắn"]

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ Tải về CSV",
        data=csv_bytes,
        file_name="leads.csv",
        mime="text/csv",
    )


# ── Cấu hình trang ──────────────────────────────────────────────────────────
st.set_page_config(page_title="LangGraph AI Agent", page_icon="🤖", layout="centered")
st.title("🤖 LangGraph AI Agent")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    _page = st.radio(
        "Trang",
        options=["💬 Chat", "📋 Danh sách Lead"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.divider()
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
        index=1,
        label_visibility="collapsed",
        help="Chọn mô hình nhúng phù hợp với ngôn ngữ tài liệu trong Knowledge Base.",
    )
    embedding_type = _EMBEDDING_OPTIONS[embedding_label]
    st.divider()

    # ── Advanced RAG Controls ─────────────────────────────────────────────────
    with st.expander("🔬 Cài đặt RAG nâng cao"):
        st.caption("Các kỹ thuật nâng cao — bật từng tính năng tùy nhu cầu.")

        use_hyde = st.checkbox(
            "HyDE (Hypothetical Document Embedding)",
            value=False,
            help=(
                "LLM tạo một đoạn văn giả thuyết từ câu hỏi, "
                "sau đó dùng vector của đoạn đó để tìm kiếm. "
                "Hiệu quả với câu hỏi ngắn, mơ hồ."
            ),
        )
        use_decomposition = st.checkbox(
            "Query Decomposition",
            value=False,
            help=(
                "Phân rã câu hỏi phức tạp thành 2-4 sub-queries đơn giản hơn, "
                "tìm kiếm từng ý rồi gộp kết quả. "
                "Hiệu quả với câu hỏi so sánh, tổng hợp đa chiều."
            ),
        )
        if use_hyde and use_decomposition:
            st.warning(
                "⚠️ Khi cả HyDE + Decomposition cùng bật, "
                "Decomposition chạy trước và sub_queries được ưu tiên — "
                "hyde_query có thể không được dùng.",
                icon="⚠️",
            )

        use_hybrid = st.checkbox(
            "Hybrid Search (BM25 + Vector + RRF)",
            value=False,
            help=(
                "Chạy song song BM25 (khớp từ khóa) và Vector Search (ngữ nghĩa), "
                "gộp bằng Reciprocal Rank Fusion. "
                "Hiệu quả với tên riêng, mã số, thuật ngữ kỹ thuật. "
                "⚠️ Yêu cầu đã ingest ít nhất một lần."
            ),
        )
        use_rerank = st.checkbox(
            "Cross-Encoder Re-ranking",
            value=False,
            help=(
                "Lấy Top-50 từ retrieval, dùng Cross-Encoder để chấm điểm lại "
                "và chọn Top-5 chính xác nhất. "
                "Chậm hơn ~2-5s nhưng chất lượng cao hơn đáng kể. "
                "⚠️ Lần chạy đầu sẽ tải model ~300-500MB."
            ),
        )
        retrieval_mode = st.selectbox(
            "Retrieval Mode",
            options=["similarity", "mmr"],
            index=0,
            help=(
                "similarity: thuần vector similarity (mặc định, nhanh).\n"
                "mmr: Maximal Marginal Relevance — đa dạng hóa kết quả, "
                "tránh trả về các chunk có nội dung lặp lại."
            ),
        )
        if retrieval_mode == "mmr" and use_rerank:
            st.info(
                "ℹ️ Cross-Encoder Reranking sẽ bị bỏ qua khi dùng MMR mode "
                "(MMR đã tối ưu diversity, rerank sẽ phá vỡ hiệu quả đó).",
                icon="ℹ️",
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
            # Bước 1: Upload từng file lên backend qua API
            saved = []
            upload_ok = True
            for f in uploaded_files:
                try:
                    r = requests.post(
                        _FILES_API_BASE,
                        files={"file": (f.name, f.getvalue())},
                        timeout=120,  # 120s để xử lý file lớn
                    )
                    r.raise_for_status()
                    saved.append(f.name)
                except requests.exceptions.ConnectionError:
                    st.error("Không kết nối được backend. Hãy chắc chắn server đang chạy.")
                    upload_ok = False
                    break
                except requests.exceptions.Timeout:
                    st.error(f"Upload '{f.name}' quá thời gian chờ. File có thể quá lớn hoặc server bận.")
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
                            json={
                                "chunk_size": 500,
                                "chunk_overlap": 50,
                                "embedding_type": embedding_type,
                                "chunking_strategy": "recursive",
                                "hnsw_preset": "balanced",
                            },
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
        st.caption("Tùy chỉnh thông số chunking, HNSW và xem trước kết quả.")

        # ── Chiến lược chunking ──────────────────────────────────────────────
        chunking_strategy = st.selectbox(
            "Chunking Strategy",
            options=["recursive", "semantic"],
            index=0,
            help=(
                "recursive: cắt theo kích thước cố định (chunk_size/overlap) — nhanh.\n"
                "semantic: phát hiện ranh giới ngữ nghĩa tự động — chậm hơn, "
                "giữ trọn vẹn ý tưởng hơn."
            ),
        )

        if chunking_strategy == "recursive":
            chunk_size = st.number_input(
                "Chunk Size",
                min_value=100, max_value=3000, value=500, step=50,
                help="Số ký tự tối đa trong mỗi chunk.",
            )
            chunk_overlap = st.number_input(
                "Chunk Overlap",
                min_value=0, max_value=500, value=50, step=10,
                help="Số ký tự chồng lấp giữa các chunk liền kề.",
            )
            breakpoint_type = "percentile"
            breakpoint_amount = 95.0
        else:
            # SemanticChunker params
            st.caption(
                "⚠️ SemanticChunker gọi embedding API nhiều lần khi chunking — "
                "có thể mất vài phút với tài liệu lớn."
            )
            breakpoint_type = st.selectbox(
                "Breakpoint Threshold Type",
                options=["percentile", "standard_deviation", "interquartile"],
                index=0,
                help=(
                    "percentile: cắt tại điểm x% cao nhất về khoảng cách ngữ nghĩa.\n"
                    "standard_deviation: cắt khi vượt ngưỡng độ lệch chuẩn.\n"
                    "interquartile: cắt dựa trên khoảng tứ phân vị."
                ),
            )
            breakpoint_amount = st.number_input(
                "Breakpoint Threshold Amount",
                min_value=0.0, max_value=100.0, value=95.0, step=1.0,
                help="Giá trị ngưỡng (ví dụ: 95.0 nghĩa là cắt tại top-5% khoảng cách).",
            )
            chunk_size = 500    # không dùng nhưng cần để gọi API
            chunk_overlap = 50

        # ── HNSW Preset ──────────────────────────────────────────────────────
        hnsw_preset = st.selectbox(
            "HNSW Index Preset",
            options=["fast", "balanced", "accurate"],
            index=1,
            help=(
                "fast: M=8, ef_construction=100, ef_search=50 (nhanh, ít RAM).\n"
                "balanced: M=16, ef_construction=200, ef_search=100 (mặc định).\n"
                "accurate: M=32, ef_construction=400, ef_search=200 (chính xác, nhiều RAM).\n"
                "⚠️ Chỉ áp dụng khi ingest lại (re-index)."
            ),
        )

        if st.button("🔄 Cập nhật Database & Xem trước Chunks", use_container_width=True):
            with st.spinner("Đang nạp lại và cắt tài liệu..."):
                try:
                    resp = requests.post(
                        _INGEST_API,
                        json={
                            "chunk_size": int(chunk_size),
                            "chunk_overlap": int(chunk_overlap),
                            "embedding_type": embedding_type,
                            "chunking_strategy": chunking_strategy,
                            "breakpoint_threshold_type": breakpoint_type,
                            "breakpoint_threshold_amount": float(breakpoint_amount),
                            "hnsw_preset": hnsw_preset,
                        },
                        timeout=300,  # SemanticChunker có thể cần đến 5 phút
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    chunks_preview = data["chunks"]
                    st.success(
                        f"Đã nạp thành công {data['total']} chunks! "
                        f"(strategy={chunking_strategy}, hnsw={hnsw_preset})"
                    )
                    for i, chunk_text in enumerate(chunks_preview, 1):
                        with st.expander(f"Chunk {i} ({len(chunk_text)} ký tự)"):
                            st.info(chunk_text)
                except requests.exceptions.ConnectionError:
                    st.error(
                        "Không kết nối được backend. "
                        "Hãy chắc chắn server đang chạy tại `http://127.0.0.1:8080`."
                    )
                except requests.exceptions.Timeout:
                    st.error("Backend mất quá nhiều thời gian phản hồi (>300s). Thử lại sau.")
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
                    # Xóa cache để danh sách tự load lại
                    st.session_state.pop("_file_list_cache", None)
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("Không kết nối được backend.")
                except Exception as e:
                    st.error(f"Lỗi tải lên: {e}")

        # Danh sách file hiện có + nút xóa
        st.markdown("**Danh sách file trong `docs/data/` :**")

        # Nút làm mới — xóa cache để gọi API lại
        if st.button("🔄 Làm mới", key="refresh_file_list"):
            st.session_state.pop("_file_list_cache", None)

        # Chỉ gọi API khi chưa có cache (tránh gọi lại mỗi lần re-render)
        if "_file_list_cache" not in st.session_state:
            try:
                r = requests.get(_FILES_API_BASE, timeout=10)
                r.raise_for_status()
                st.session_state["_file_list_cache"] = r.json().get("files", [])
            except requests.exceptions.ConnectionError:
                st.warning("⚠️ Chưa kết nối được backend. Nhấn 🔄 để thử lại.")
                st.session_state["_file_list_cache"] = None
            except Exception as e:
                st.warning(f"Lỗi tải danh sách: {e}")
                st.session_state["_file_list_cache"] = None

        file_list = st.session_state.get("_file_list_cache")
        if file_list is None:
            pass  # thông báo đã hiển thị ở trên
        elif not file_list:
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
                        st.session_state.pop("_file_list_cache", None)
                        st.rerun()
                    except requests.exceptions.ConnectionError:
                        st.error("Không kết nối được backend.")
                    except Exception as e:
                        st.error(f"Lỗi xóa: {e}")

if _page == "📋 Danh sách Lead":
    _leads_page()
    st.stop()

# ── Thanh trạng thái: kỹ thuật RAG đang bật ──────────────────────────────────
_active_badges: list[str] = []
if use_hyde:            _active_badges.append("🧠 HyDE")
if use_decomposition:   _active_badges.append("✂️ Decomp")
if use_hybrid:          _active_badges.append("🔀 Hybrid")
if use_rerank:          _active_badges.append("🎯 Rerank")
if retrieval_mode == "mmr": _active_badges.append("🌈 MMR")

_embed_label_short = "🇻🇳 VI" if embedding_type == "vi" else "🇺🇸 EN"

if _active_badges:
    st.info(
        f"{_embed_label_short}  |  **Kỹ thuật đang bật:** {' · '.join(_active_badges)}",
        icon="⚡",
    )
else:
    st.caption(f"{_embed_label_short}  |  Chế độ: Pure Vector Search (mặc định)")

# ── Khởi tạo lịch sử tin nhắn trong session state ────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
# Lưu metadata (badges) để hiển thị lại trong lịch sử
if "messages_meta" not in st.session_state:
    st.session_state.messages_meta = []

# ── Hiển thị toàn bộ lịch sử hội thoại ──────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # Hiển thị badge kỹ thuật đã dùng cho mỗi lượt assistant
        if msg["role"] == "assistant" and i < len(st.session_state.messages_meta):
            meta = st.session_state.messages_meta[i]
            if meta.get("badges"):
                st.caption("⚡ " + " · ".join(meta["badges"]))
        st.write(msg["content"])

# ── Ô nhập liệu ──────────────────────────────────────────────────────────────
if prompt := st.chat_input("Nhập câu hỏi của bạn..."):
    # Build payload để gửi — lưu lại để debug
    _payload = {
        "query": prompt,
        "thread_id": thread_id,
        "embedding_type": embedding_type,
        "use_hyde": use_hyde,
        "use_decomposition": use_decomposition,
        "use_hybrid": use_hybrid,
        "use_rerank": use_rerank,
        "retrieval_mode": retrieval_mode,
    }

    # Hiển thị tin nhắn người dùng + badge kỹ thuật ngay lập tức
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.messages_meta.append({})
    with st.chat_message("user"):
        st.write(prompt)
        if _active_badges:
            st.caption("Gửi với: " + " · ".join(_active_badges))

    # Gọi backend với tất cả Advanced RAG params
    with st.chat_message("assistant"):
        with st.spinner(f"Đang xử lý... {'(' + ', '.join(_active_badges) + ')' if _active_badges else ''}"):
            try:
                response = requests.post(
                    _API_URL,
                    json=_payload,
                    timeout=120,
                )
                response.raise_for_status()
                answer = response.json()["answer"]
                _success = True
            except requests.exceptions.ConnectionError:
                answer = (
                    "⚠️ Không kết nối được backend. "
                    "Hãy chắc chắn server đang chạy tại `http://127.0.0.1:8080`."
                )
                _success = False
            except requests.exceptions.Timeout:
                answer = "⚠️ Backend mất quá nhiều thời gian phản hồi (>120s). Thử lại sau."
                _success = False
            except Exception as e:
                answer = f"⚠️ Lỗi không xác định: {e}"
                _success = False

        # Hiển thị badge kỹ thuật đã dùng ngay trên câu trả lời
        if _active_badges and _success:
            st.caption("⚡ " + " · ".join(_active_badges))
        st.write(answer)

        # Debug expander: xem chính xác params đã gửi
        with st.expander("🔍 Debug — Params đã gửi tới API"):
            st.json(_payload)

    # Lưu phản hồi + metadata vào lịch sử
    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.messages_meta.append({"badges": _active_badges.copy()})
