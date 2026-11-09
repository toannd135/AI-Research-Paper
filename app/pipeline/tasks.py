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


def _save_validation_report(task_id: str, report: dict | None) -> None:
    """Ghi validation_report.json để người dùng kiểm tra từng lỗi (không chặn task nếu không ghi được)."""
    if not report:
        return
    try:
        import json
        from pathlib import Path

        from app.core.config import get_settings

        path = Path(get_settings().upload_dir) / "validation" / f"{task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError:
        logger.exception("Không ghi được validation_report cho task %s", task_id)


def _save_ledger_csv(db, task_id: str, results: list[dict] | None) -> None:
    """Supplementary: <upload_dir>/ledger/<task_id>.csv (không chặn task nếu không ghi được)."""
    if not results:
        return
    try:
        from pathlib import Path

        from sqlalchemy import select

        from app.agent.evidence.ledger_export import export_ledger_csv
        from app.api.models.paper import Paper
        from app.core.config import get_settings

        ids = {r.get("paper_id") for r in results}
        files = {p.id: p.filename for p in db.scalars(select(Paper).where(Paper.id.in_(ids)))}
        n = export_ledger_csv(results, Path(get_settings().upload_dir) / "ledger" / f"{task_id}.csv", files)
        logger.info("Đã xuất %d bản ghi sổ cái cho task %s", n, task_id)
    except Exception:
        logger.exception("Không xuất được sổ cái CSV cho task %s", task_id)


def _research_scope(db, allowed: set[str] | None) -> set[str] | None:
    """Phạm vi truy xuất = paper đã xử lý xong trong DB (giao với phạm vi người dùng).

    Vector trong Qdrant của paper đã xóa khỏi DB (mồ côi) không có metadata -> thành reference 'Anonymous'/UUID
    và làm sai số paper; vì vậy kể cả admin cũng chỉ thấy paper có trong DB. DB chưa có paper done -> giữ phạm vi cũ.
    """
    from sqlalchemy import select

    from app.api.models.paper import Paper

    done = set(db.scalars(select(Paper.id).where(Paper.status == PaperStatus.DONE.value)).all())
    if not done:
        logger.warning("Chưa có paper nào xử lý xong; research chạy trên toàn bộ vector hiện có")
        return allowed
    return done if allowed is None else allowed & done


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
            from app.core.scope import allowed_paper_ids_for, set_allowed_paper_ids, set_local_only

            owner = db.get(User, task.user_id) if task.user_id else None
            set_allowed_paper_ids(_research_scope(db, allowed_paper_ids_for(db, owner, task.workspace_id)))
            set_local_only(bool(task.workspace_id))
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
            _save_validation_report(task_id, state.get("validation_report"))
            _save_ledger_csv(db, task_id, state.get("results"))
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
        from app.core.scope import set_allowed_paper_ids, set_local_only

        set_allowed_paper_ids(None)
        set_local_only(False)
        db.close()
