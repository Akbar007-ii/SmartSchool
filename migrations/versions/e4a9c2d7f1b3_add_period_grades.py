"""add_period_grades

Чейректик (Q1–Q4) жана жылдык (YEAR) жыйынтык баалар.
Мугалим чейректин орточо баасын көрүп, жыйынтык бааны өзү коёт.

Revision ID: e4a9c2d7f1b3
Revises: b7d3f1a2c9e4
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e4a9c2d7f1b3'
down_revision: Union[str, Sequence[str], None] = 'b7d3f1a2c9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'period_grades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assignment_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=4), nullable=False),
        sa.Column('grade_value', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('grade_value >= 2 AND grade_value <= 5', name='check_period_grade_value'),
        sa.CheckConstraint("period IN ('Q1', 'Q2', 'Q3', 'Q4', 'YEAR')", name='check_period_grade_period'),
        sa.ForeignKeyConstraint(['assignment_id'], ['teacher_assignments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['student_id'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id', 'student_id', 'period', name='unique_period_grade'),
    )
    op.create_index(op.f('ix_period_grades_id'), 'period_grades', ['id'], unique=False)
    op.create_index(op.f('ix_period_grades_assignment_id'), 'period_grades', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_period_grades_student_id'), 'period_grades', ['student_id'], unique=False)
    op.create_index(op.f('ix_period_grades_school_id'), 'period_grades', ['school_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_period_grades_school_id'), table_name='period_grades')
    op.drop_index(op.f('ix_period_grades_student_id'), table_name='period_grades')
    op.drop_index(op.f('ix_period_grades_assignment_id'), table_name='period_grades')
    op.drop_index(op.f('ix_period_grades_id'), table_name='period_grades')
    op.drop_table('period_grades')
