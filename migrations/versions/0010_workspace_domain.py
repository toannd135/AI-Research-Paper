"""workspaces.domain: chế độ nghiên cứu của kho (general | mri_brain | deepfake)

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("domain", sa.String(length=32), nullable=False, server_default="general"))


def downgrade() -> None:
    op.drop_column("workspaces", "domain")
