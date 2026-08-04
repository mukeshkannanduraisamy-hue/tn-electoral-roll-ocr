"""chat message turn meta

Revision ID: 59f6a10e6e33
Revises: b1c2d3e4f5a6
Create Date: 2026-08-04 15:25:38.451847

`budget_exhausted` and `provider_notice` carry the two agent-loop signals
that Task 11's review flagged as easy to swallow: a turn that ran out of
rounds/calls/wall-clock, and a provider failure kept out of the answer
prose. Both are guard-enforced facts about the turn, not model output, so
they belong on the row alongside the reply rather than folded into
`tool_trace`.

Note: this autogenerate run also detected a pre-existing, unrelated drift
(a missing index on `chat_threads.created_at`, left out of the Task 1
migration despite the model declaring `index=True`). That is out of scope
here and intentionally not included -- fixing it belongs in whichever
change owns `chat_threads`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59f6a10e6e33'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'budget_exhausted', sa.Boolean(), nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column('provider_notice', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_column('provider_notice')
        batch_op.drop_column('budget_exhausted')
