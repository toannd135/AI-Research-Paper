"""Kiểm tra một research task chỉ trích dẫn paper nằm trong một thư mục nguồn (vd. data/papers_deepfake).

    python scripts/verify_task_sources.py --task <task_id> --dir data/papers_deepfake

Chỉ đọc DB. Thoát mã 1 nếu task có citation ngoài thư mục (nguồn ngoài như OpenAlex, hoặc paper của đề tài khác).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.models.research_task import ResearchTask
from app.core.database import SessionLocal
from app.pipeline.seed import foreign_citation_ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True)
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        task = db.get(ResearchTask, args.task)
        if task is None:
            print("Không tìm thấy task")
            return 2
        ids = [c.get("paper_id", "") for c in json.loads(task.citations or "[]")]
        foreign = foreign_citation_ids(db, ids, Path(args.dir))
        print(
            f"task {task.status} | workspace {task.workspace_id} | citation {len(set(ids))} paper | ngoài {args.dir}: {len(foreign)}"
        )
        for pid in foreign:
            print(" -", pid)
        print(
            "OK: mọi reference đều từ thư mục nguồn"
            if not foreign and ids
            else "KHÔNG ĐẠT"
            if foreign
            else "Task chưa có citation"
        )
        return 1 if foreign else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
