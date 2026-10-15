"""Test nhanh khâu tổng hợp bài báo + xuất PDF, bỏ qua search/analyze/critique.

Lấy câu hỏi, draft (= report cũ) và citations từ một research task đã có trong DB.

    docker compose exec -e PYTHONPATH=/app api python scripts/quick_paper.py [task_id] [survey|novel_research]

Kết quả: /app/quick_paper.md và /app/quick_paper.pdf (nằm ở thư mục AI-Research-Paper trên máy host).
"""

import json
import sys
import time

from sqlalchemy import select

from app.agent.nodes.synthesize_node import synthesize_node
from app.api.models.research_task import ResearchTask
from app.core.database import SessionLocal
from app.core.schemas import Citation
from app.pipeline.export.pdf_renderer import report_to_pdf

task_id = sys.argv[1] if len(sys.argv) > 1 and len(sys.argv[1]) > 10 else None
mode = next((a for a in sys.argv[1:] if a in ("survey", "novel_research")), "survey")

with SessionLocal() as db:
    stmt = select(ResearchTask).where(ResearchTask.report.is_not(None)).order_by(ResearchTask.created_at.desc())
    task = db.get(ResearchTask, task_id) if task_id else db.scalars(stmt).first()

state = {
    "question": task.refined_question or task.question,
    "draft": task.report,
    "citations": [Citation(**c) for c in json.loads(task.citations or "[]")],
    "research_mode": mode,
}
print(f"Task {task.id} | mode={mode} | {len(state['citations'])} citations")

t0 = time.time()
report = synthesize_node(state)["report"]
print(f"Tổng hợp xong sau {time.time() - t0:.0f}s, {len(report):,} ký tự")
open("quick_paper.md", "w", encoding="utf-8").write(report)

t0 = time.time()
open("quick_paper.pdf", "wb").write(report_to_pdf(report))
print(f"PDF xong sau {time.time() - t0:.0f}s → quick_paper.pdf")
