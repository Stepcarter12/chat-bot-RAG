# AI Chatbot System

Tài liệu tham chiếu tĩnh dành cho AI Agent và lập trình viên.

---

## 1. Project Overview

Hệ thống Chatbot AI tùy chỉnh, được chuyển đổi từ bản nguyên mẫu low-code sang kiến trúc mã nguồn mở hoàn chỉnh.

Mục tiêu cốt lõi:
- Kiểm soát toàn bộ luồng xử lý và logic nghiệp vụ thay vì phụ thuộc vào nền tảng bên thứ ba.
- Khả năng mở rộng linh hoạt: thêm công cụ, tích hợp nguồn dữ liệu, và tùy chỉnh hành vi Agent.
- Triển khai độc lập trên hạ tầng tự quản lý.

---

## 2. Tech Stack

| Lớp | Công nghệ | Vai trò |
|---|---|---|
| **API Layer** | FastAPI (Python) | Backend REST API, xử lý yêu cầu từ client |
| **Orchestration** | LangGraph | Điều phối luồng hội thoại và trạng thái Agent |
| **Vector Database** | ChromaDB | Lưu trữ và tìm kiếm ngữ nghĩa cho RAG |
| **Memory** | LangGraph Checkpointer | Quản lý bộ nhớ hội thoại theo phiên và dài hạn |
| **LLM** | Claude (Anthropic) | Mô hình ngôn ngữ chính |

---

## 3. Directory Architecture

```
.
├── docs/               # Kiến thức & Quy trình
│   ├── project/        # Tài liệu tĩnh: kiến trúc, ERD, đặc tả tính năng
│   └── process/        # Tài liệu động: ADR, ghi chú họp, kế hoạch triển khai
├── ops/                # Hạ tầng & Công cụ vận hành
│   └── ...             # Docker, CI/CD, script triển khai
└── src/                # Mã nguồn sản phẩm
    └── ...             # backend/, frontend/, shared/
```

**`docs/`** — Ngữ cảnh cho AI Agent. Agent đọc thư mục này để hiểu *cái gì* đang được xây dựng, *tại sao*, và *quyết định nào đã được đưa ra* — không cần hỏi lại.

**`ops/`** — Toàn bộ cấu hình hạ tầng, tách biệt hoàn toàn khỏi logic sản phẩm. Agent không nhầm lẫn giữa "deploy tooling" và "product code".

**`src/`** — Điểm trung tâm duy nhất cho mã nguồn. Mọi component sản phẩm đều nằm ở đây.

---

## 4. Development Roadmap

| Phase | Tên | Nội dung |
|---|---|---|
| **Phase 1** | FastAPI Framework | Thiết lập cấu trúc dự án, endpoint cơ bản, xác thực, và middleware |
| **Phase 2** | LangGraph & Memory | Tích hợp LangGraph, triển khai Checkpointer cho bộ nhớ hội thoại |
| **Phase 3** | RAG & Tools | Kết nối ChromaDB, xây dựng pipeline RAG, tích hợp công cụ ngoài |
| **Phase 4** | Optimization & Hooks | Tối ưu hiệu năng, thêm Claude Code Hooks, giám sát và logging |

---

*Tài liệu này được duy trì như nguồn sự thật duy nhất (single source of truth) cho toàn bộ dự án.*
