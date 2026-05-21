# Tổng kết Dự án AI Chatbot — Phase 1 → 4

## Trạng thái tổng quan

| Phase | Tên | Trạng thái |
|-------|-----|-----------|
| Phase 1 | Nền tảng & Khung API | ✅ Hoàn thành |
| Phase 2 | LangGraph & Bộ nhớ | ✅ Hoàn thành |
| Phase 3 | RAG & Conditional Edges | ✅ Hoàn thành |
| Phase 4 | Optimization & Hooks | ✅ Hoàn thành |

---

## ✅ Phase 1 — Nền Tảng & Khung API

**Mục tiêu:** Thiết lập cấu trúc dự án chuẩn, khởi tạo môi trường, và xây dựng máy chủ FastAPI cơ bản.

### Đã hoàn thành

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Tạo môi trường ảo Python | `venv/` | Cô lập dependencies |
| Định nghĩa thư viện lõi | `requirements.txt` | fastapi, uvicorn, pydantic, python-dotenv, langgraph, langchain-core, langchain-groq, langchain-huggingface, chromadb, sentence-transformers, langchain-community, langchain-text-splitters |
| Cấu trúc thư mục chuẩn | `src/api/`, `src/core/`, `src/services/`, `src/retrieval/`, `docs/project/`, `docs/process/` | Phân tách rõ ràng |
| Biến môi trường | `.env` | Chứa `GROQ_API_KEY` |
| Khởi tạo FastAPI app | `src/main.py` | CORS middleware, prefix `/api/v1` |
| API endpoint chat | `src/api/routes.py` | `POST /api/v1/chat` nhận `query` + `thread_id` |
| Health check | `src/main.py` | `GET /health` → `{"status": "ok"}` |
| Tài liệu kiến trúc | `docs/project/dify-logic-mapping.md` | Ánh xạ từ Dify sang LangGraph |
| Quy ước dự án | `CLAUDE.md` | Import `src.`, comment tiếng Việt, type hints |

### Luồng dữ liệu Phase 1
```
Client → POST /api/v1/chat { query, thread_id } → FastAPI → [response placeholder]
```

---

## ✅ Phase 2 — LangGraph & Bộ Nhớ

**Mục tiêu:** Thay thế luồng Dify bằng LangGraph StateGraph, tích hợp bộ nhớ hội thoại tự động.

### Đã hoàn thành

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Định nghĩa State trung tâm | `src/services/graph_service.py` | `ChatbotState(TypedDict)` với `messages`, `context`, `needs_retrieval` |
| Reducer `add_messages` | `graph_service.py` | `Annotated[list[BaseMessage], add_messages]` — tự động gắn thêm message vào danh sách |
| LLM Node | `graph_service.py` | `call_llm_node()` — gọi Groq (`llama-3.1-8b-instant`), trả `AIMessage` |
| Checkpointer bộ nhớ | `graph_service.py` | `MemorySaver` compile cùng đồ thị — lưu toàn bộ State theo `thread_id` |
| Kết nối vào FastAPI | `src/api/routes.py` | `graph_app.invoke()` với `config = {"configurable": {"thread_id": ...}}` |

### Cấu trúc State
```python
class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # lịch sử hội thoại
    context: str        # ngữ cảnh RAG
    needs_retrieval: bool  # kết quả phân loại câu hỏi
```

### Luồng dữ liệu Phase 2
```
POST /api/v1/chat
  → graph_app.invoke({ messages }, config={ thread_id })
  → call_llm_node → AIMessage
  → MemorySaver lưu State theo thread_id
```

---

## ✅ Phase 3 — RAG & Conditional Edges

**Mục tiêu:** Xây dựng pipeline RAG nội bộ với ChromaDB, thêm logic rẽ nhánh thông minh.

### Đã hoàn thành

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Kết nối ChromaDB | `src/retrieval/vector_store.py` | Collection `knowledge_base`, persist tại `./chroma_data` |
| Embedding model | `vector_store.py` | `HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")` |
| Tìm kiếm với ngưỡng | `vector_store.py` | `similarity_search_with_relevance_scores()` + filter `score >= 0.5` |
| Question Classifier Node | `graph_service.py` | `question_classifier_node()` — LLM phân loại "yes/no" có cần RAG |
| Hàm router | `graph_service.py` | `route_after_classifier()` — trả tên node tiếp theo |
| Conditional Edges | `graph_service.py` | `add_conditional_edges()` — rẽ nhánh dựa trên `needs_retrieval` |
| Retrieval Node | `graph_service.py` | `retrieval_node()` — truy xuất context từ ChromaDB |
| Script nạp dữ liệu | `src/retrieval/ingest.py` | Load `.txt` từ `docs/data/`, chunk 500/50, lưu vào ChromaDB |
| Thư mục tài liệu | `docs/data/.gitkeep` | Nơi người dùng bỏ file tài liệu thô |

### Luồng đồ thị hiện tại
```
START
  → question_classifier_node (LLM phân loại yes/no)
      → [needs_retrieval=True]  → retrieval_node → call_llm_node → END
      → [needs_retrieval=False]               → call_llm_node → END
```

### Cách chạy ingest
```bash
# Bỏ file .txt vào docs/data/, sau đó chạy:
python src/retrieval/ingest.py
# Output: Đã nạp thành công 42 chunks vào ChromaDB.
```

---

## ✅ Phase 4 — Optimization & Hooks

**Mục tiêu (theo README):** Tối ưu hiệu năng, thêm Claude Code Hooks, giám sát và logging.

### Lỗi/Gap cần vá trước

#### Gap 1 🔴 — `ingest.py` tạo duplicate khi chạy nhiều lần
**File:** `src/retrieval/ingest.py:33`
`Chroma.from_documents()` không kiểm tra trùng lặp — mỗi lần chạy sẽ nạp thêm toàn bộ dữ liệu cũ vào collection.

**Sửa:** Xóa collection cũ trước khi nạp lại.
```python
# Thêm vào ingest_documents() trước Chroma.from_documents():
_old = Chroma(
    collection_name="knowledge_base",
    embedding_function=embeddings,
    persist_directory=_CHROMA_DIR,
)
_old.delete_collection()
```

#### Gap 2 🔴 — `src/core/utils.py` thiếu theo spec
**Tài liệu:** `dify-logic-mapping.md` ghi: *"Code Node → Standard Functions trong `src/core/utils.py`"*
**Sửa:** Tạo file này với logger dùng chung (xem Nhiệm vụ 4.1 bên dưới).

#### Gap 3 🟡 — `routes.py` truyền `"context": ""` vào State
**File:** `src/api/routes.py:26`
Khi LangGraph restore State từ checkpoint, `"context": ""` có thể ghi đè context đã lưu.

**Sửa:**
```python
# Trước:
result = graph_app.invoke(
    {"messages": [HumanMessage(content=request.query)], "context": ""},
    config=config,
)
# Sau:
result = graph_app.invoke(
    {"messages": [HumanMessage(content=request.query)]},
    config=config,
)
```

---

### Nhiệm vụ Phase 4

#### 4.1 — Tạo `src/core/utils.py` (Logger dùng chung)
**File mới:** `src/core/utils.py`
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def get_logger(name: str) -> logging.Logger:
    """Trả về logger chuẩn cho module."""
    return logging.getLogger(name)
```

#### 4.2 — Tích hợp logging vào nodes & routes
**Files sửa:** `src/services/graph_service.py`, `src/api/routes.py`

```python
# Ví dụ trong graph_service.py
from src.core.utils import get_logger
_logger = get_logger(__name__)

def question_classifier_node(state: ChatbotState) -> dict:
    ...
    _logger.info("Phân loại câu hỏi: needs_retrieval=%s", needs)
    return {"needs_retrieval": needs}
```

#### 4.3 — Tạo `setup.cfg` (cấu hình linting)
**File mới:** `setup.cfg` tại thư mục gốc
```ini
[flake8]
max-line-length = 100
exclude =
    venv/,
    __pycache__/,
    chroma_data/

[mypy]
python_version = 3.10
ignore_missing_imports = True
strict = False
```

**Thêm vào `requirements.txt`:**
```
flake8
mypy
```

#### 4.4 — Tạo `.claude/settings.json` (Claude Code Hooks)
**File mới:** `.claude/settings.json`
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python -m flake8 src/ --max-line-length=100 --exclude=venv,__pycache__ 2>&1 | head -20"
          }
        ]
      }
    ]
  }
}
```

#### 4.5 — Nâng cấp `/health` endpoint
**File sửa:** `src/main.py`
```python
@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_model": "llama-3.1-8b-instant",
        "vector_store": "chromadb",
    }
```

#### 4.6 — Pin phiên bản trong `requirements.txt`
Chạy `pip freeze` trong venv để pin versions cụ thể, tránh xung đột khi deploy.

---

### Thứ tự thực thi Phase 4

| # | Việc | File | Ưu tiên |
|---|------|------|---------|
| 1 | Sửa duplicate trong `ingest.py` | `src/retrieval/ingest.py` | 🔴 Cao |
| 2 | Tạo `src/core/utils.py` với logger | `src/core/utils.py` | 🔴 Cao |
| 3 | Tích hợp log vào nodes & routes | `graph_service.py`, `routes.py` | 🟡 Trung bình |
| 4 | Bỏ `"context": ""` khỏi initial state | `src/api/routes.py` | 🟡 Trung bình |
| 5 | Tạo `setup.cfg` + thêm flake8/mypy | `setup.cfg`, `requirements.txt` | 🟡 Trung bình |
| 6 | Tạo `.claude/settings.json` hooks | `.claude/settings.json` | 🟢 Thấp |
| 7 | Nâng cấp `/health` endpoint | `src/main.py` | 🟢 Thấp |
| 8 | Pin versions | `requirements.txt` | 🟢 Thấp |

---

## Kiểm tra sau khi hoàn thành Phase 4

```bash
# 1. Linting
python -m flake8 src/ --max-line-length=100

# 2. Type check
python -m mypy src/

# 3. Ingest không duplicate (chạy 2 lần, số chunk phải bằng nhau)
python src/retrieval/ingest.py
python src/retrieval/ingest.py

# 4. Khởi động server và kiểm tra log
uvicorn src.main:app --reload
# → xem terminal có log: [INFO] Phân loại câu hỏi: needs_retrieval=True/False

# 5. Health check
curl http://localhost:8000/health

# 6. Test end-to-end
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "sản phẩm X có giá bao nhiêu?", "thread_id": "test-1"}'
```
