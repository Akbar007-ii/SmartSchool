"""email_login_without_personal_data

Логин ИННдин ордуна электрондук почта болот. Жеке маалыматтар өчүрүлөт:
колдонуучунун ИННи жана телефону, мектептин дареги жана телефону.
Предметтин коду да өчүрүлөт (колдонулган эмес).

Мурунку колдонуучуларга орун басар почта берилет: user<id>@smartschool.local.
Почтаны өзгөртүүчү эндпоинт жок: чыныгы колдонуучулары бар базада
миграциядан кийин почталарды SQL менен толтуруу же аккаунттарды кайра түзүү керек.

Revision ID: a9e1c4b7d2f6
Revises: f2b8d4a6c1e9
Create Date: 2026-11-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a9e1c4b7d2f6'
down_revision: Union[str, Sequence[str], None] = 'f2b8d4a6c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(length=254), nullable=True))
    op.execute("UPDATE users SET email = 'user' || id || '@smartschool.local'")
    op.alter_column('users', 'email', nullable=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.drop_constraint('check_inn_format', 'users', type_='check')
    op.drop_index(op.f('ix_users_inn'), table_name='users')
    op.drop_column('users', 'inn')
    op.drop_column('users', 'phone')

    op.drop_column('schools', 'address')
    op.drop_column('schools', 'phone')

    op.drop_column('subjects', 'code')


def downgrade() -> None:
    op.add_column('subjects', sa.Column('code', sa.String(length=30), nullable=True))

    op.add_column('schools', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column('schools', sa.Column('address', sa.String(length=300), nullable=True))

    op.add_column('users', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('inn', sa.String(length=14), nullable=True))
    # ИНН кайра калыбына келбейт: id боюнча 14 цифралуу орун басар коюлат
    op.execute("UPDATE users SET inn = lpad(id::text, 14, '0')")
    op.alter_column('users', 'inn', nullable=False)
    op.create_index(op.f('ix_users_inn'), 'users', ['inn'], unique=True)
    op.create_check_constraint('check_inn_format', 'users', "inn ~ '^[0-9]{14}$'")

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_column('users', 'email')
