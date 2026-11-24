"""parent_code_email_notifications

Окуучунун ата-эне коду (ата-эне баланы ушул код менен байлайт)
жана билдирүүлөрдү почтага жөнөтүү жөндөөсү.

Revision ID: b4d6f8a1c3e5
Revises: a9e1c4b7d2f6
Create Date: 2026-11-24 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b4d6f8a1c3e5'
down_revision: Union[str, Sequence[str], None] = 'a9e1c4b7d2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('parent_code', sa.String(length=12), nullable=True))
    op.create_unique_constraint('uq_users_parent_code', 'users', ['parent_code'])
    op.add_column(
        'users',
        sa.Column('email_notifications', sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'email_notifications')
    op.drop_constraint('uq_users_parent_code', 'users', type_='unique')
    op.drop_column('users', 'parent_code')
