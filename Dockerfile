# ── Image chung cho FastAPI, Celery Worker, Flower, Streamlit ────────────────
# Dùng python:3.11-slim để giảm kích thước image
FROM python:3.11-slim

# Tắt compile .pyc files để giảm số lượng file ghi vào disk
# Giúp tránh lỗi I/O khi Docker unpack layer trên WSL2
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cài system dependencies:
# - libpq-dev: header PostgreSQL (cần cho psycopg[binary])
# - gcc: biên dịch một số C-extension của sentence-transformers
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Cài Python dependencies trước (tận dụng Docker cache layer)
COPY requirements.txt .

# Cài torch CPU-only TRƯỚC để tránh kéo ~1.5GB CUDA packages
# --no-compile: không tạo .pyc, giảm số file cần ghi vào overlay filesystem
RUN pip install --no-cache-dir --no-compile \
    torch \
    torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --no-compile -r requirements.txt

# Pre-download embedding models vào image để worker không phải tải lúc runtime
# Không có cache → lần đầu gọi RAG mất 30-60s tải model từ HuggingFace
# Có cache trong image → worker load model ngay lập tức (~1s)
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
print('Downloading all-MiniLM-L6-v2 (en)...'); \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
print('Downloading multilingual-e5-small (vi)...'); \
SentenceTransformer('intfloat/multilingual-e5-small'); \
print('Models cached OK')"

# Copy toàn bộ source code
COPY . .

# Mặc định chạy FastAPI (có thể override qua docker-compose command)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
