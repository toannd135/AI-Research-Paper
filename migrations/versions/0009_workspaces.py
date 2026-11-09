"""workspaces (phiên/đề tài) + papers.workspace_id, research_tasks.workspace_id

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])
    for table in ("papers", "research_tasks"):
        op.add_column(table, sa.Column("workspace_id", sa.String(length=36), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])


def downgrade() -> None:
    for table in ("research_tasks", "papers"):
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_table("workspaces")
