"""curriculum_programs

Окуу программасы (календардык-тематикалык план): программа предмет+параллель боюнча,
анын темалары жана ар бир класстын прогресси.

Revision ID: d1f3a5c7e9b2
Revises: c7e9a2b4d6f8
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd1f3a5c7e9b2'
down_revision: Union[str, Sequence[str], None] = 'c7e9a2b4d6f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'curriculum_programs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id'), nullable=False),
        sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('grade_number', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('school_id', 'subject_id', 'grade_number', name='unique_school_program'),
        sa.CheckConstraint('grade_number >= 1 AND grade_number <= 11', name='check_program_grade'),
    )
    op.create_index(op.f('ix_curriculum_programs_id'), 'curriculum_programs', ['id'])
    op.create_index(op.f('ix_curriculum_programs_school_id'), 'curriculum_programs', ['school_id'])

    op.create_table(
        'curriculum_topics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('program_id', sa.Integer(), sa.ForeignKey('curriculum_programs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=200), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('hours', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('week', sa.Integer(), nullable=True),
        sa.Column('goals', sa.Text(), nullable=True),
        sa.Column('materials', sa.Text(), nullable=True),
    )
    op.create_index(op.f('ix_curriculum_topics_id'), 'curriculum_topics', ['id'])
    op.create_index(op.f('ix_curriculum_topics_program_id'), 'curriculum_topics', ['program_id'])

    op.create_table(
        'curriculum_progress',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('class_id', sa.Integer(), sa.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('curriculum_topics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('done_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('marked_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('class_id', 'topic_id', name='unique_class_topic_progress'),
    )
    op.create_index(op.f('ix_curriculum_progress_id'), 'curriculum_progress', ['id'])
    op.create_index(op.f('ix_curriculum_progress_class_id'), 'curriculum_progress', ['class_id'])


def downgrade() -> None:
    op.drop_table('curriculum_progress')
    op.drop_table('curriculum_topics')
    op.drop_table('curriculum_programs')
