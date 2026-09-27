"""POST /chat, GET /conversations."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGatewayError
from app.ai.llm_gateway.base import Message as LLMMessage
from app.ai.llm_gateway.registry import (
    AVAILABLE_MODELS,
    build_gateway,
    is_configured,
    resolve_model,
)
from app.ai.retrieval.hybrid import search_hybrid
from app.ai.retrieval.reranker import rerank
from app.api.models.conversation import Conversation
from app.api.models.conversation import Message as MessageModel
from app.core.database import get_db
from app.core.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])

_SYSTEM_PROMPT = (
    "Bạn là trợ lý nghiên cứu khoa học. Chỉ trả lời dựa trên context được cung cấp, "
    "trích dẫn nguồn bằng ký hiệu [n] tương ứng. Nếu context không đủ để trả lời, hãy nói rõ là không đủ thông tin."
)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    candidates = search_hybrid(payload.question, top_k=20, paper_id=payload.paper_id)
    top_chunks = rerank(payload.question, candidates, top_k=6)
    if not top_chunks:
        raise HTTPException(status_code=404, detail="Không tìm thấy nội dung liên quan để trả lời")

    context_text, citations = build_context(top_chunks)
    conversation = _get_or_create_conversation(db, payload.conversation_id, payload.paper_id)

    model_option = resolve_model(payload.model)
    try:
        llm = build_gateway(model_option)
        response = llm.generate(
            messages=[
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f"Context:\n{context_text}\n\nCâu hỏi: {payload.question}"),
            ],
            model_name=model_option.model_name,
        )
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add(MessageModel(conversation_id=conversation.id, role="user", content=payload.question))
    db.add(MessageModel(conversation_id=conversation.id, role="assistant", content=response.text))
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id, answer=response.text, citations=citations, model=model_option.id
    )


@router.get("/chat/models")
def list_chat_models():
    return [
        {"id": option.id, "label": option.label, "available": is_configured(option)}
        for option in AVAILABLE_MODELS
    ]


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    conversations = db.query(Conversation).order_by(Conversation.created_at.desc()).all()
    return [{"id": c.id, "paper_id": c.paper_id, "created_at": c.created_at} for c in conversations]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation không tồn tại")
    return {
        "id": conversation.id,
        "paper_id": conversation.paper_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at} for m in conversation.messages
        ],
    }


def _get_or_create_conversation(db: Session, conversation_id: str | None, paper_id: str | None) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            return conversation
    conversation = Conversation(paper_id=paper_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation
