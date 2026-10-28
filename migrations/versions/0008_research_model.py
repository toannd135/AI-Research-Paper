"""research_tasks: contribution_type, target_venue, user_results, research_model (Research Knowledge Model)

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_tasks", sa.Column("contribution_type", sa.String(length=20), nullable=True))
    op.add_column("research_tasks", sa.Column("target_venue", sa.String(length=120), nullable=True))
    op.add_column("research_tasks", sa.Column("user_results", sa.Text(), nullable=True))
    op.add_column("research_tasks", sa.Column("research_model", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("research_model", "user_results", "target_venue", "contribution_type"):
        op.drop_column("research_tasks", col)
