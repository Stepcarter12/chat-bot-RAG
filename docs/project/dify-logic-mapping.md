# Ánh xạ Logic từ Dify ChatFlow sang Hệ thống Custom

Tài liệu này ghi lại logic cốt lõi của nguyên mẫu (prototype) trên Dify để làm căn cứ cho Claude Code chuyển đổi sang mã nguồn LangGraph.

---

## 1. Luồng xử lý dữ liệu (The Flow)

Dựa trên ChatFlow của Dify, hệ thống hoạt động theo đồ thị có hướng (Directed Graph) sau:

```
Bắt đầu → Phân loại ý định → Truy xuất tri thức (RAG) → Xử lý LLM → Kết thúc
```

---

## 2. Chi tiết các Node & Logic nghiệp vụ

### A. Start Node — Điểm khởi đầu

- **Mô tả:** Tiếp nhận yêu cầu từ người dùng qua API.
- **Biến đầu vào:**
  - `query` *(string)*: Câu hỏi của người dùng.
  - `thread_id` *(string)*: ID phiên để quản lý bộ nhớ (Memory).
- **Biến đầu ra:** Đẩy `query` vào State trung tâm.

---

### B. Question Classifier — Phân loại ý định

- **Logic:** Sử dụng LLM để phân tích xem người dùng đang hỏi về:
  - **Kiến thức chuyên môn** → Cần truy xuất tài liệu (RAG).
  - **Trò chuyện thông thường** → Đi thẳng tới LLM.
- **System Prompt:**
  > "Bạn là bộ phân loại câu hỏi. Hãy xác định câu hỏi sau có cần tra cứu tài liệu không. Trả về `True` hoặc `False`."

---

### C. Knowledge Retrieval — RAG Node

- **Logic:** Tìm kiếm ngữ cảnh trong Vector Database *(ChromaDB thay thế cho Knowledge Base của Dify)*.
- **Tham số:**
  - `top_k` = `3`
  - `score_threshold` = `0.5`
- **Đầu ra:** Danh sách các đoạn văn bản liên quan (`context_chunks`).

---

### D. LLM Node — Xử lý chính

- **Model:** Claude 3.5 Sonnet hoặc GPT-4o.
- **System Prompt:**
  > "Bạn là một trợ lý thông minh. Sử dụng nội dung trong phần [Context] để trả lời câu hỏi. Nếu thông tin không có trong [Context], hãy trả lời dựa trên kiến thức chung nhưng phải trung thực."
- **Biến đầu vào:** `query`, `context_chunks`, `history` *(lấy từ bộ nhớ)*.

---

## 3. Quy tắc ánh xạ kỹ thuật (Mapping Rules)

| Thành phần Dify | Chuyển đổi sang Code (OOP / LangGraph) |
|---|---|
| **Variable Assigner** | Cập nhật trực tiếp vào đối tượng `State` (Python `TypedDict`) |
| **Edges (Cạnh)** | `Conditional Edges` trong LangGraph điều hướng dựa trên logic hàm |
| **History / Memory** | `Checkpointer` (`MemorySaver`) tự động lưu trạng thái vào SQLite |
| **Code Node** | Các hàm Python thuần (Standard Functions) trong `src/core/utils.py` |
