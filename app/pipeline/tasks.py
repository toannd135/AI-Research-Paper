"""Celery task: process_paper(), run_research()."""

from app.core.database import SessionLocal
from app.core.schemas import PaperStatus
from app.pipeline.chunking.semantic_chunker import chunk_pages
from app.pipeline.parser.pdf_parser import parse_pdf
from app.pipeline.vector_store.qdrant_client import ensure_collection, upsert_chunks
from app.workers.celery_app import celery_app


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

        paper.status = PaperStatus.PROCESSING
        paper.error = None
        db.commit()

        try:
            pages = parse_pdf(paper.file_path)
            chunks = chunk_pages(paper_id, pages)
            if not chunks:
                raise ValueError("Không trích xuất được nội dung từ PDF")

            vectors = embed_batch([c.text for c in chunks])
            ensure_collection(vector_size=len(vectors[0]))
            upsert_chunks(chunks, vectors)

            paper.status = PaperStatus.DONE
            db.commit()
            return {"paper_id": paper_id, "chunks": len(chunks)}
        except Exception as exc:
            paper.status = PaperStatus.FAILED
            paper.error = str(exc)
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
            raise ValueError(f"ResearchTask {task_id} không tồn tại")

        task.status = ResearchStatus.PROCESSING.value
        task.error = None
        db.commit()

        try:
            question = task.refined_question or task.question
            state = run_graph(question)

            from app.agent.format_sanitizer import sanitize_academic_markdown

            task.report = sanitize_academic_markdown(state.get("report", ""))
            task.citations = json.dumps([c.model_dump() for c in state.get("citations", [])])
            task.status = ResearchStatus.DONE.value
            db.commit()
            return {"task_id": task_id, "status": task.status}
        except Exception as exc:
            task.status = ResearchStatus.FAILED.value
            task.error = str(exc)
            db.commit()
            raise
    finally:
        db.close()
