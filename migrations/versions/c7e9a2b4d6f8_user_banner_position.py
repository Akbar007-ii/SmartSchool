"""user_banner_position

Мектептин баннерин колдонуучу өзүнө жылдырган абал аккаунтта сакталат
(мурда браузерде гана болчу — башка түзмөктө кайра ортого келчү).

Revision ID: c7e9a2b4d6f8
Revises: b4d6f8a1c3e5
Create Date: 2026-11-24 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7e9a2b4d6f8'
down_revision: Union[str, Sequence[str], None] = 'b4d6f8a1c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('banner_position', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'banner_position')
