"""initial schema - swaps, prices, holders, transfers, sync_state

Baseline migration. The DB was created from db/init.sql before Alembic
was added. This empty migration marks the starting point so future
autogenerate diffs work correctly.

Revision ID: 13aad4e7b153
Revises:
Create Date: 2026-02-26 17:41:38.712686

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '13aad4e7b153'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline — schema already exists from init.sql."""
    pass


def downgrade() -> None:
    """Nothing to downgrade for baseline."""
    pass
