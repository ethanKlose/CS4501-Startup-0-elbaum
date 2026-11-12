"""Add a custom protein target without changing existing profiles or plans."""
from alembic import op
import sqlalchemy as sa

revision = '0002_protein_target'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('profiles')}
    if 'protein_target' not in columns:
        op.add_column('profiles', sa.Column('protein_target', sa.Integer(), nullable=True))


def downgrade():
    raise RuntimeError('Downgrade is blocked to preserve saved protein targets.')
