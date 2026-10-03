"""Test ORM ResearchTask tạo bảng và roundtrip trên SQLite in-memory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.models.research_task import ResearchTask
from app.core.database import Base
from app.core.schemas import ResearchStatus


def test_research_task_create_and_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        task = ResearchTask(id="t1", question="So sánh A và B", status=ResearchStatus.PENDING.value)
        session.add(task)
        session.commit()

        loaded = session.get(ResearchTask, "t1")
        assert loaded is not None
        assert loaded.question == "So sánh A và B"
        assert loaded.status == ResearchStatus.PENDING.value
        assert loaded.report is None
