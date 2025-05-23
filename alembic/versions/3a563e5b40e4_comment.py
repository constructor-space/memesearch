"""comment

Revision ID: 3a563e5b40e4
Revises: ca43c9d79693
Create Date: 2025-04-29 22:02:49.715403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a563e5b40e4'
down_revision: Union[str, None] = 'ca43c9d79693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('image', sa.Column('phash', sa.String(), nullable=False))
    op.drop_constraint('image_sha256_key', 'image', type_='unique')
    op.create_unique_constraint(None, 'image', ['phash'])
    op.drop_column('image', 'sha256')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('image', sa.Column('sha256', sa.VARCHAR(), autoincrement=False, nullable=False))
    op.drop_constraint(None, 'image', type_='unique')
    op.create_unique_constraint('image_sha256_key', 'image', ['sha256'])
    op.drop_column('image', 'phash')
    # ### end Alembic commands ###
