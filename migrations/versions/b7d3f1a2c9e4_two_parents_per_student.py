"""two_parents_per_student

Окуучуга эки ата-эне (апа жана ата) байланса болот.
Мурунку чектөө (бир окуучу — бир ата-эне) алынып, бир эле жуп кайталанбашы үчүн
(parent_id, student_id) уникалдуулугу коюлат. Санды (эң көп 2) API текшерет.

Revision ID: b7d3f1a2c9e4
Revises: 88251a5458a7
Create Date: 2026-11-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d3f1a2c9e4'
down_revision: Union[str, Sequence[str], None] = '88251a5458a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('unique_student_parent', 'parent_students', type_='unique')
    op.create_unique_constraint('unique_parent_student', 'parent_students', ['parent_id', 'student_id'])


def downgrade() -> None:
    # Эскертүү: эки ата-энеси бар окуучулар болсо, кайтаруу ишке ашпайт.
    op.drop_constraint('unique_parent_student', 'parent_students', type_='unique')
    op.create_unique_constraint('unique_student_parent', 'parent_students', ['student_id'])
