"""Celery task: process_paper(), run_research()."""

import logging

from app.core.database import SessionLocal
from app.core.schemas import PaperStatus
from app.pipeline.chunking.semantic_chunker import chunk_pages
from app.pipeline.figures import extract_figures, figures_dir
from app.pipeline.parser.pdf_parser import parse_pdf
from app.pipeline.vector_store.qdrant_client import delete_paper, ensure_collection, upsert_chunks
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.pipeline.tasks.process_paper")
def process_paper(paper_id: str) -> dict:
    """Parse -> chunk -> embed -> lưu Qdrant cho 1 paper, cập nhật Paper.status."""
    from app.ai.embedding.service import embed_batch
    from app.api.models.paper import Paper

    db = SessionLocal()
    try:
        paper = db.get(Paper, paper_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} không tồn tại")

        paper.status = PaperStatus.PROCESSING.value
        paper.error = None
        db.commit()

        try:
            pages = parse_pdf(paper.file_path)
            chunks = chunk_pages(paper_id, pages)
            if not chunks:
                raise ValueError("Không trích xuất được nội dung từ PDF")

            vectors = embed_batch([c.text for c in chunks])
            ensure_collection(vector_size=len(vectors[0]))
            delete_paper(paper_id)  # idempotent: lập chỉ mục lại không tạo vector trùng
            upsert_chunks(chunks, vectors)

            # Hình thật kèm chú thích để đưa vào bài báo; lỗi trích hình không làm hỏng việc lập chỉ mục.
            try:
                figures = extract_figures(paper.file_path, figures_dir(paper_id), source_title=paper.filename)
                logger.info("Paper %s: trích %d hình có chú thích", paper_id, len(figures))
            except Exception:
                logger.warning("Paper %s: không trích được hình", paper_id, exc_info=True)

            paper.status = PaperStatus.DONE.value
            db.commit()
            logger.info("Paper %s xử lý xong: %d chunk", paper_id, len(chunks))
            return {"paper_id": paper_id, "chunks": len(chunks)}
        except Exception as exc:
            logger.exception("Paper %s xử lý thất bại", paper_id)
            paper.status = PaperStatus.FAILED.value
            paper.error = str(exc)[:2000]
            db.commit()
            raise
    finally:
        db.close()


@celery_app.task(name="app.pipeline.tasks.run_research")
def run_research(task_id: str) -> dict:
    """Chạy LangGraph research agent cho 1 ResearchTask, cập nhật report/citations/status."""
    import json

    from app.agent.graph import run_graph
    from app.api.models.research_task import ResearchTask
    from app.core.schemas import ResearchStatus

    db = SessionLocal()
    try:
        task = db.get(ResearchTask, task_id)
        if task is None:
            # Phiên đã bị xoá khi tác vụ còn nằm trong hàng đợi: bỏ qua, không coi là lỗi.
            logger.info("Research task %s không còn tồn tại, bỏ qua", task_id)
            return {"task_id": task_id, "status": "deleted"}

        task.status = ResearchStatus.PROCESSING.value
        task.error = None
        db.commit()

        try:
            from app.api.models.user import User
            from app.core.scope import allowed_paper_ids_for, set_allowed_paper_ids

            owner = db.get(User, task.user_id) if task.user_id else None
            set_allowed_paper_ids(allowed_paper_ids_for(db, owner))
            question = task.refined_question or task.question
            state = run_graph(
                question,
                audience=task.audience,
                field=task.field,
                contribution_type=task.contribution_type,
                target_venue=task.target_venue,
                user_results=task.user_results,
            )

            from app.agent.format_sanitizer import sanitize_academic_markdown

            db.expire_all()
            task = db.get(ResearchTask, task_id)
            if task is None:
                logger.info("Research task %s đã bị xoá trong lúc chạy, bỏ qua kết quả", task_id)
                return {"task_id": task_id, "status": "deleted"}
            task.report = sanitize_academic_markdown(state.get("report", ""))
            task.citations = json.dumps([c.model_dump() for c in state.get("citations", [])])
            task.contribution_type = state.get("contribution_type")
            task.research_model = json.dumps(state["research_model"]) if state.get("research_model") else None
            task.status = ResearchStatus.DONE.value
            db.commit()
            logger.info("Research task %s hoàn tất: report %d ký tự", task_id, len(task.report or ""))
            return {"task_id": task_id, "status": task.status}
        except Exception as exc:
            logger.exception("Research task %s thất bại", task_id)
            db.rollback()
            task = db.get(ResearchTask, task_id)
            if task is None:
                return {"task_id": task_id, "status": "deleted"}
            task.status = ResearchStatus.FAILED.value
            task.error = str(exc)[:2000]
            db.commit()
            raise
    finally:
        from app.core.scope import set_allowed_paper_ids

        set_allowed_paper_ids(None)
        db.close()
