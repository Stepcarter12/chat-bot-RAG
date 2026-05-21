from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router

app = FastAPI(
    title="AI Chatbot API",
    version="1.0.0",
)

# Cấu hình CORS cho môi trường development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn router với prefix chuẩn RESTful
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_model": "llama-3.1-8b-instant",
        "vector_store": "chromadb",
    }
