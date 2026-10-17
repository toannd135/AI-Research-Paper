"""Lập chỉ mục lại toàn bộ paper trong DB vào Qdrant (dùng khi vector store bị reset/mất dữ liệu).

Cách dùng:
    python scripts/reindex_papers.py            # chỉ in ra việc sẽ làm
    python scripts/reindex_papers.py --apply    # thực hiện

Paper mất file PDF trên đĩa sẽ được đánh dấu `failed` (kèm lý do) thay vì giữ trạng thái `done` sai sự thật.
"""

import argparse
import os

from app.api.models.paper import Paper
from app.core.database import SessionLocal
from app.core.schemas import PaperStatus
from app.pipeline.tasks import process_paper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="thực hiện lập chỉ mục (mặc định chỉ in kế hoạch)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        papers = db.query(Paper).all()
        for paper in papers:
            exists = os.path.exists(paper.file_path)
            print(f"{paper.id[:8]}  {paper.filename}  {'có file' if exists else 'MẤT FILE'}")
            if not args.apply:
                continue
            if exists:
                print("   ->", process_paper(paper.id))
            else:
                paper.status = PaperStatus.FAILED.value
                paper.error = "File PDF không còn trên đĩa; hãy tải lên lại để lập chỉ mục."
                db.commit()
        if not args.apply:
            print("\nDry-run: thêm --apply để thực hiện.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
