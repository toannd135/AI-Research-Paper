"""research_tasks.audience/field: đối tượng đọc và lĩnh vực của bài báo

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("audience", sa.String(length=20), nullable=True))
    op.add_column("research_tasks", sa.Column("field", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("research_tasks", "field")
    op.drop_column("research_tasks", "audience")
