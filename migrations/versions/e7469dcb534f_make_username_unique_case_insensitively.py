"""make username unique case-insensitively

ユーザー名の重複チェックを、大文字・小文字を区別しない形に変える。
（Taro と taro を同じ名前とみなす）

Revision ID: e7469dcb534f
Revises: d96ac129be18
Create Date: 2026-11-19 05:16:10.184869

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7469dcb534f'
down_revision = 'd96ac129be18'
branch_labels = None
depends_on = None


def upgrade():
    # lower(username) に対する重複禁止のインデックスを作る
    # （Alembic の自動検出では見つけられないため手で書いている）
    op.create_index(
        'uq_users_username_lower',
        'users',
        [sa.text('lower(username)')],
        unique=True,
    )
    # 大文字・小文字を区別する古いインデックスは不要になったので消す
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_username')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_username', ['username'], unique=True)
    op.drop_index('uq_users_username_lower', table_name='users')
