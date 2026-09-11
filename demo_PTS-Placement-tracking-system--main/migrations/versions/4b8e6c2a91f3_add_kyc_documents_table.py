"""add kyc_documents table for per-document KYC approval

Revision ID: 4b8e6c2a91f3
Revises: 9f3c1a7d5e21
Create Date: 2026-09-11 00:00:00.000000

Adds a `kyc_documents` table so each uploaded KYC document (PAN, GST
certificate, registration certificate, bank details, authorized person's
Aadhaar) has its own Pending/Approved/Rejected status, per SRS FR-06.

`organizations.kyc_status` is left in place unchanged - it now represents
the organization's overall/derived KYC state (see
app/services/kyc.py:recompute_organization_kyc_status), computed from
these per-document rows rather than being set directly by hand for orgs
that have documents uploaded. Existing organizations with no documents
yet keep whatever kyc_status they already have.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '4b8e6c2a91f3'
down_revision = '9f3c1a7d5e21'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'kyc_documents',
        sa.Column('id', mysql.CHAR(length=32), nullable=False),
        sa.Column('organization_id', sa.BigInteger(), nullable=False),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('uploaded_by', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('kyc_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_kyc_documents_organization_id'), ['organization_id'], unique=False)

    # IMPORTANT: the app used to save "VERIFIED" from the Organization edit
    # form's KYC dropdown, but every other screen (list badges, detail page,
    # and the new login-gate check) has always compared against "APPROVED".
    # Normalize old data now so organizations that were already
    # verified/approved don't suddenly get their users locked out of login
    # the moment this deploy ships the login-gating check.
    op.execute("UPDATE organizations SET kyc_status = 'APPROVED' WHERE kyc_status = 'VERIFIED'")

    # Grandfather clause: KYC-gated login is a brand new enforcement - it
    # never existed before this deploy, so most existing organizations
    # were never bothered to get formally marked APPROVED (there was no
    # reason to). Auto-approve anything sitting at PENDING or with no
    # kyc_status set at all, so the entire existing customer base isn't
    # locked out the moment this ships. Deliberately excludes REJECTED
    # organizations, since those were explicitly flagged for a reason and
    # should go through a real review before being let back in.
    op.execute("UPDATE organizations SET kyc_status = 'APPROVED' WHERE kyc_status = 'PENDING' OR kyc_status IS NULL")


def downgrade():
    with op.batch_alter_table('kyc_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_kyc_documents_organization_id'))
    op.drop_table('kyc_documents')