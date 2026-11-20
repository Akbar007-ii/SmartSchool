"""announcement_audience

Жарыя кимдер үчүн: STUDENT, PARENT, TEACHER, DEPUTY үтүр менен.
NULL — баарына.

Revision ID: f2b8d4a6c1e9
Revises: e4a9c2d7f1b3
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f2b8d4a6c1e9'
down_revision: Union[str, Sequence[str], None] = 'e4a9c2d7f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('announcements', sa.Column('audience', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('announcements', 'audience')
