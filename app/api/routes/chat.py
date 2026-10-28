"""POST /chat, GET /conversations."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.language import ENGLISH_ONLY_RULE
from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGatewayError
from app.ai.llm_gateway.base import Message as LLMMessage
from app.ai.llm_gateway.registry import (
    build_gateway,
    get_available_models,
    is_configured,
    resolve_model,
)
from app.ai.retrieval.hybrid import search_hybrid
from app.ai.retrieval.reranker import rerank
from app.api.deps import can_access, get_current_user
from app.api.models.conversation import Conversation
from app.api.models.conversation import Message as MessageModel
from app.api.models.paper import Paper
from app.api.models.research_task import ResearchTask
from app.api.models.user import ROLE_ADMIN, User
from app.core.database import get_db
from app.core.schemas import ChatRequest, ChatResponse
from app.core.scope import allowed_paper_ids_for, filter_chunks

router = APIRouter(tags=["chat"], dependencies=[Depends(get_current_user)])

_SYSTEM_PROMPT = (
    "Bạn là trợ lý nghiên cứu khoa học. Chỉ trả lời dựa trên context được cung cấp, "
    "trích dẫn nguồn bằng ký hiệu [n] tương ứng. Nếu context không đủ để trả lời, hãy nói rõ là không đủ thông tin.\n\n"
    + ENGLISH_ONLY_RULE
)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ChatResponse:
    if payload.paper_id:
        paper = db.get(Paper, payload.paper_id)
        if paper is None or not can_access(user, paper.user_id):
            raise HTTPException(status_code=404, detail="Paper không tồn tại")
    if payload.research_task_id:
        task = db.get(ResearchTask, payload.research_task_id)
        if task is None or not can_access(user, task.user_id):
            raise HTTPException(status_code=404, detail="Research task không tồn tại")
    # Truy xuất toàn kho rồi lọc theo paper của người dùng để không lộ nội dung người khác.
    allowed = allowed_paper_ids_for(db, user)
    candidates = filter_chunks(search_hybrid(payload.question, top_k=60, paper_id=payload.paper_id), allowed)[:20]
    top_chunks = rerank(payload.question, candidates, top_k=6)
    if not top_chunks:
        raise HTTPException(status_code=404, detail="Không tìm thấy nội dung liên quan để trả lời")

    context_text, citations = build_context(top_chunks)
    conversation = _get_or_create_conversation(
        db, payload.conversation_id, payload.paper_id, payload.research_task_id, user
    )

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
    db.add(MessageModel(
            conversation_id=conversation.id,
            role="assistant",
            content=response.text,
            citations=json.dumps([c.model_dump() for c in citations], ensure_ascii=False) if citations else None,
        ))
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id, answer=response.text, citations=citations, model=model_option.id
    )


@router.get("/chat/models")
def list_chat_models():
    return [
        {"id": option.id, "label": option.label, "available": is_configured(option)}
        for option in get_available_models()
    ]


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Conversation)
    if user.role != ROLE_ADMIN:
        query = query.filter(Conversation.user_id == user.id)
    conversations = query.order_by(Conversation.created_at.desc()).all()
    return [{"id": c.id, "paper_id": c.paper_id, "created_at": c.created_at} for c in conversations]


@router.get("/conversations/by-research/{task_id}")
def get_conversation_by_research(
    task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Hội thoại hỏi đáp gắn với một phiên nghiên cứu (mới nhất); rỗng nếu chưa có."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.research_task_id == task_id)
        .filter(Conversation.user_id == user.id if user.role != ROLE_ADMIN else True)
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if conversation is None:
        return {"id": None, "paper_id": None, "messages": []}
    return get_conversation(conversation.id, db, user)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or not can_access(user, conversation.user_id):
        raise HTTPException(status_code=404, detail="Conversation không tồn tại")
    return {
        "id": conversation.id,
        "paper_id": conversation.paper_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "citations": json.loads(m.citations) if m.citations else [],
                "created_at": m.created_at,
            }
            for m in conversation.messages
        ],
    }


def _get_or_create_conversation(
    db: Session,
    conversation_id: str | None,
    paper_id: str | None,
    research_task_id: str | None,
    user: User,
) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None and can_access(user, conversation.user_id):
            return conversation
    conversation = Conversation(paper_id=paper_id, research_task_id=research_task_id, user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation
