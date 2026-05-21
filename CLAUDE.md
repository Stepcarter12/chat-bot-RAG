# Quy ước dự án

- Tuân thủ Type Hinting của Python 3.10+.
- Trước khi viết code mới, luôn kiểm tra thư mục `docs/project/` để nắm yêu cầu.
- Sử dụng tiếng Việt trong các comment code.

## Quy ước Import Python

- Server luôn được khởi động từ thư mục **gốc** của dự án bằng lệnh `uvicorn src.main:app --reload`.
- Do đó, tất cả các import bên trong `src/` phải dùng prefix `src.` để Python giải quyết đúng đường dẫn.
- **Đúng:** `from src.services.graph_service import app`
- **Sai:** `from services.graph_service import app` (gây `ModuleNotFoundError` vì `services` không nằm trong root)
