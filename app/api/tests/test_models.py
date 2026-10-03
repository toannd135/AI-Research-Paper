"""Test ORM models tạo bảng và roundtrip trên SQLite in-memory (không cần Postgres thật)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.models.conversation import Conversation, Message
from app.api.models.paper import Paper
from app.core.database import Base
from app.core.schemas import PaperStatus


def test_models_create_tables_and_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        paper = Paper(id="p1", filename="a.pdf", file_path="/tmp/a.pdf", status=PaperStatus.PENDING.value)
        session.add(paper)
        session.commit()

        conversation = Conversation(id="c1", paper_id="p1")
        session.add(conversation)
        session.commit()

        message = Message(id="m1", conversation_id="c1", role="user", content="hello")
        session.add(message)
        session.commit()

        loaded = session.get(Conversation, "c1")
        assert loaded is not None
        assert loaded.messages[0].content == "hello"
        assert loaded.messages[0].role == "user"
