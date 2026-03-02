"""add swap indexes for search and ML

Revision ID: 209d9e9747ad
Revises: 13aad4e7b153
Create Date: 2026-02-27 14:53:25.187465

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '209d9e9747ad'
down_revision: Union[str, Sequence[str], None] = '13aad4e7b153'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add indexes for wallet search and ML queries."""
    op.create_index('idx_swaps_recipient_timestamp', 'swaps', ['recipient', 'timestamp'], unique=False)
    op.create_index('idx_swaps_amount_usdt', 'swaps', ['amount_usdt'], unique=False)
    op.create_index('idx_swaps_is_buy_timestamp', 'swaps', ['is_buy', 'timestamp'], unique=False)


def downgrade() -> None:
    """Remove search/ML indexes."""
    op.drop_index('idx_swaps_is_buy_timestamp', table_name='swaps')
    op.drop_index('idx_swaps_amount_usdt', table_name='swaps')
    op.drop_index('idx_swaps_recipient_timestamp', table_name='swaps')
