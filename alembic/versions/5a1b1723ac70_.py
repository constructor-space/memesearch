"""empty message

Revision ID: 5a1b1723ac70
Revises: 1fb8a1776a28, b5ea3879404a
Create Date: 2025-05-16 19:35:48.214403

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1b1723ac70'
down_revision: Union[str, None] = ('1fb8a1776a28', 'b5ea3879404a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
