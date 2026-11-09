"""Gán chủ sở hữu cho các paper trong một thư mục, để user thường chỉ thấy paper của đề tài mình.

Cách dùng (chạy từ thư mục gốc repo):
    python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake survey"   # dry-run
    python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake survey" --apply

Chỉ ghi `papers.user_id`/`papers.workspace_id` (và tạo workspace nếu thêm --workspace). User phải đã đăng ký (POST /auth/register).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.pipeline.seed import assign_papers_to_user


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="thư mục chứa PDF của đề tài")
    ap.add_argument("--email", required=True, help="email người dùng sẽ sở hữu các paper")
    ap.add_argument("--workspace", help="tên phiên/đề tài (tạo nếu chưa có) để gán cho các paper")
    ap.add_argument("--apply", action="store_true", help="thực hiện (mặc định chỉ in kế hoạch)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        changed = assign_papers_to_user(db, Path(args.dir), args.email, apply=args.apply, workspace_name=args.workspace)
        for p in changed:
            print(f"{p.id[:8]}  {p.filename}  (chủ cũ: {p.user_id})")
        print(
            f"\n{len(changed)} paper {'đã gán' if args.apply else 'sẽ gán (dry-run, thêm --apply để thực hiện)'} cho {args.email}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
