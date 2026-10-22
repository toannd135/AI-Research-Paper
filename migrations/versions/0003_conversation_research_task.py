"""conversations.research_task_id

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("research_task_id", sa.String(length=36), nullable=True))
    op.create_index("ix_conversations_research_task_id", "conversations", ["research_task_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_research_task_id", table_name="conversations")
    op.drop_column("conversations", "research_task_id")
