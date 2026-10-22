"""papers.content_hash (sha256) để nhập PDF có sẵn mà không tạo bản ghi trùng

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_papers_content_hash", "papers", ["content_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_papers_content_hash", table_name="papers")
    op.drop_column("papers", "content_hash")
