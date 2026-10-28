"""site public : événements CDE et signalements

Revision ID: a7c1e9d2f400
Revises: 6614f189d782
Create Date: 2026-10-28 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c1e9d2f400'
down_revision = '6614f189d782'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title_fr', sa.String(length=160), nullable=False),
        sa.Column('title_ar', sa.String(length=160), nullable=False),
        sa.Column('body_fr', sa.Text(), nullable=True),
        sa.Column('body_ar', sa.Text(), nullable=True),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('place', sa.String(length=160), nullable=True),
        sa.Column('wilaya_id', sa.Integer(), nullable=True),
        sa.Column('institute_id', sa.Integer(), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['institute_id'], ['institute.id']),
        sa.ForeignKeyConstraint(['wilaya_id'], ['wilaya.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('event', schema=None) as b:
        b.create_index(b.f('ix_event_starts_on'), ['starts_on'], unique=False)
        b.create_index(b.f('ix_event_wilaya_id'), ['wilaya_id'], unique=False)
        b.create_index(b.f('ix_event_institute_id'), ['institute_id'], unique=False)

    op.create_table(
        'ticket',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ref', sa.String(length=12), nullable=False),
        sa.Column('token', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=150), nullable=True),
        sa.Column('wilaya_id', sa.Integer(), nullable=True),
        sa.Column('institute_id', sa.Integer(), nullable=True),
        sa.Column('subject', sa.String(length=160), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('reply', sa.Text(), nullable=True),
        sa.Column('handled_by_id', sa.Integer(), nullable=True),
        sa.Column('handled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['handled_by_id'], ['user.id']),
        sa.ForeignKeyConstraint(['institute_id'], ['institute.id']),
        sa.ForeignKeyConstraint(['wilaya_id'], ['wilaya.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ref'),
        sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('ticket', schema=None) as b:
        b.create_index(b.f('ix_ticket_created_at'), ['created_at'], unique=False)
        b.create_index(b.f('ix_ticket_wilaya_id'), ['wilaya_id'], unique=False)
        b.create_index(b.f('ix_ticket_institute_id'), ['institute_id'], unique=False)


def downgrade():
    op.drop_table('ticket')
    op.drop_table('event')
