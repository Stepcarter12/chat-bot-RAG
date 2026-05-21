from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.core.utils import get_logger
from src.services.graph_service import ChatbotState, app as graph_app

router = APIRouter()
_logger = get_logger(__name__)


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
    _logger.info("Nhận request: thread_id=%s, query='%s'", request.thread_id, request.query)
    config: RunnableConfig = {"configurable": {"thread_id": request.thread_id}}
    initial_state: ChatbotState = {
        "messages": [HumanMessage(content=request.query)],
        "context": "",
        "needs_retrieval": False,
    }
    result = graph_app.invoke(initial_state, config=config)
    answer = result["messages"][-1].content
    _logger.info("Trả lời xong: thread_id=%s", request.thread_id)
    return ChatResponse(answer=answer, thread_id=request.thread_id)
