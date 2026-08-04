# AI Chatbot System

Tài liệu tham chiếu tĩnh dành cho AI Agent và lập trình viên.

---

## 1. Project Overview

Chatbot AI bán hàng điện tử — nhân vật **"Hân"** — tích hợp Facebook Messenger, được chuyển đổi từ bản nguyên mẫu low-code (Dify ChatFlow) sang kiến trúc mã nguồn mở hoàn chỉnh, dùng RAG song ngữ Anh/Việt để tư vấn sản phẩm và thu thập lead khách hàng.

Mục tiêu cốt lõi:
- Kiểm soát toàn bộ luồng xử lý và logic nghiệp vụ thay vì phụ thuộc vào nền tảng bên thứ ba.
- Khả năng mở rộng linh hoạt: thêm công cụ, tích hợp nguồn dữ liệu, và tùy chỉnh hành vi Agent.
- Triển khai độc lập trên hạ tầng tự quản lý (Docker Compose, tự host trên VPS).

---

## 2. Tech Stack

| Lớp | Công nghệ | Vai trò |
|---|---|---|
| **API Layer** | FastAPI (Python) | Backend REST API + webhook Facebook Messenger |
| **Orchestration** | LangGraph | Điều phối luồng hội thoại và trạng thái Agent |
| **LLM** | Groq (`llama-3.3-70b-versatile`) | Mô hình ngôn ngữ chính, qua `langchain-groq` |
| **Vector Database** | ChromaDB | Lưu trữ và tìm kiếm ngữ nghĩa cho RAG, 2 collection tách riêng Anh/Việt |
| **Memory** | LangGraph Checkpointer (PostgresSaver) | Quản lý bộ nhớ hội thoại theo phiên, persistent qua PostgreSQL |
| **Async Queue** | Celery + Redis | Xử lý tin nhắn Messenger bất đồng bộ (né timeout 10s của Facebook) |
| **Lead Storage** | Google Sheets (`gspread`) | Lưu số điện thoại và sản phẩm khách quan tâm |
| **Frontend** | Streamlit | Chat thử nghiệm, quản lý tài liệu RAG, xem danh sách lead |
| **Deploy** | Docker Compose, nginx, Let's Encrypt | Container hoá toàn bộ stack, SSL cho production |

---

## 3. Directory Architecture

```
.
├── docs/               # Kiến thức & Quy trình
│   ├── project/        # Tài liệu tĩnh: kiến trúc, ánh xạ thiết kế gốc
│   ├── process/        # Tài liệu động: nhật ký triển khai theo phase
│   └── data/            # Tài liệu thô để ingest vào RAG (không commit)
├── ops/                # Placeholder cho tooling vận hành (hiện chưa dùng —
│                        # cấu hình Docker/nginx đang đặt ở thư mục gốc, xem mục 5)
└── src/                # Mã nguồn sản phẩm
    ├── api/            # routes.py (REST), messenger.py (webhook Facebook)
    ├── core/           # Tiện ích dùng chung (logger, ...)
    ├── frontend/        # Giao diện Streamlit
    ├── retrieval/       # ingest.py, vector_store.py — pipeline RAG/ChromaDB
    └── services/        # graph_service.py (LangGraph), celery_app.py, lead_service.py
```

**`docs/`** — Ngữ cảnh cho AI Agent. Agent đọc thư mục này để hiểu *cái gì* đang được xây dựng, *tại sao*, và *quyết định nào đã được đưa ra* — không cần hỏi lại.

**`ops/`** — Dự kiến chứa hạ tầng/CI-CD tách biệt khỏi logic sản phẩm; hiện tại các file Docker/nginx thực tế vẫn nằm ở thư mục gốc, chưa di chuyển vào đây.

**`src/`** — Điểm trung tâm duy nhất cho mã nguồn. Mọi component sản phẩm đều nằm ở đây.

---

## 4. Development Roadmap

| Phase | Tên | Trạng thái |
|---|---|---|
| **Phase 1–4** | Nền tảng FastAPI, LangGraph & Memory, RAG cơ bản, Optimization & Hooks | ✅ Hoàn thành |
| **Phase 5–8** | Frontend Streamlit, RAG production fixes, quản lý chunk/ingest, đa ngôn ngữ (Anh/Việt), quản lý file tài liệu | ✅ Hoàn thành |
| **Phase 9** | Docker Compose + Celery + Facebook Messenger + PostgreSQL checkpoint | ✅ Hoàn thành |
| **Phase 10** | Advanced RAG — Semantic Chunking, Hybrid Search (BM25+Vector+RRF), HyDE, Query Decomposition, Cross-Encoder Rerank, MMR | ✅ Hoàn thành |
| **Phase 11** | Bot bán hàng "Hân" — system prompt, lead capture, tích hợp Google Sheets | ✅ Hoàn thành |
| **Phase 12** | Audit bảo mật, hiệu năng & chất lượng code | ✅ Hoàn thành |
| **Phase 13** | Production hardening — dedup tin nhắn, rate limit, health check thật, CORS theo env | ✅ Hoàn thành |
| **Phase 14** | HTTPS & deploy production — nginx reverse proxy, Let's Encrypt | ✅ Hoàn thành |
| **Phase 15** | Automated tests — pytest cho webhook, verify HMAC, deduplication | ⏳ Chưa thực hiện |
| **Phase 16** | Admin UI — xem lịch sử hội thoại Messenger, monitor trong Streamlit | ⏳ Chưa thực hiện |

Chi tiết từng phase (file thay đổi, bug đã sửa, quyết định kỹ thuật) xem tại [`docs/process/project-plan.md`](docs/process/project-plan.md).

---

## 5. Vận hành nhanh

```powershell
# Dev — chạy trực tiếp không Docker
uvicorn src.main:app --reload --port 8080
streamlit run src/frontend/app.py

# Hoặc dựng toàn bộ stack qua Docker (api, worker, postgres, redis, flower, streamlit)
docker compose up --build

# Production (thêm nginx + certbot cho SSL)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Chi tiết biến môi trường cần thiết xem [`.env.example`](.env.example).

---

*Tài liệu này được duy trì như nguồn sự thật duy nhất (single source of truth) cho toàn bộ dự án.*
