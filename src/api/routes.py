from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


# Schema đầu vào - ánh xạ từ Start Node trong dify-logic-mapping.md
class ChatRequest(BaseModel):
    query: str       # câu hỏi của người dùng
    thread_id: str   # định danh phiên để quản lý bộ nhớ


# Schema đầu ra
class ChatResponse(BaseModel):
    answer: str
    thread_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    # TODO Phase 2: thay mock response bằng LangGraph pipeline
    mock_answer = f"[Mock] Đã nhận câu hỏi: '{request.query}'"
    return ChatResponse(answer=mock_answer, thread_id=request.thread_id)
