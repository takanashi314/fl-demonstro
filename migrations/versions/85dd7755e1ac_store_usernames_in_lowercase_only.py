"""store usernames in lowercase only

ユーザー名を半角英小文字と数字だけにするルールに合わせて、
保存されているユーザー名を小文字にそろえ、普通の重複禁止のインデックスに切り替える。

Revision ID: 85dd7755e1ac
Revises: e7469dcb534f
Create Date: 2026-11-19 07:16:02.561344

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '85dd7755e1ac'
down_revision = 'e7469dcb534f'
branch_labels = None
depends_on = None


def upgrade():
    # 1. 今あるユーザー名を小文字にそろえる。
    #    これまでは大文字・小文字を区別しない重複禁止があったので、そろえても重複しない。
    op.execute("UPDATE users SET username = lower(username)")

    # 2. 普通の重複禁止のインデックスを作る（名前がすべて小文字になったので、これで足りる）
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    # 3. lower(username) を使った式インデックスは不要になったので消す。
    #    式インデックスは Alembic の自動検出の対象外で、SQLite でテーブルを作り直す
    #    操作をすると黙って消えてしまうため、使わないことにした。
    #    （自動生成では検出されないので、手で書いている）
    op.drop_index('uq_users_username_lower', table_name='users')


def downgrade():
    # 小文字にそろえたユーザー名は元に戻せない（元の大文字・小文字の情報がないため）
    op.create_index(
        'uq_users_username_lower',
        'users',
        [sa.text('lower(username)')],
        unique=True,
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))
