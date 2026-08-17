"""create voter_master_view

Revision ID: d8e9f0a1b2c3
Revises: 7743375bcf7b
Create Date: 2026-08-17 10:00:00.000000

Creates a comprehensive database view `voter_master_view` consolidating all
essential voter information, polling station details, source file/page
provenance, photo references, and audit timestamps into a single flat row per voter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, Sequence[str], None] = '7743375bcf7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VIEW_NAME = "voter_master_view"

CREATE_VIEW_SQL = f"""
CREATE VIEW {VIEW_NAME} AS
SELECT 
    v.id AS voter_id,
    v.epic,
    v.serial,
    v.name AS voter_name,
    v.relation_type,
    v.relation_name,
    v.house_number,
    v.age,
    v.gender,
    v.section_name,
    v.part_number,
    v.constituency,
    v.is_deleted,
    v.deletion_reason,
    v.verified,
    v.notes,
    
    -- Polling station details
    COALESCE(ps.name, '') AS polling_station_name,
    COALESCE(ps.name_tam, '') AS polling_station_name_tam,
    COALESCE(ps.building_name, '') AS building_name,
    COALESCE(ps.address, '') AS polling_station_address,
    COALESCE(ps.ac_number, '') AS ac_number,
    COALESCE(ps.ac_name, '') AS ac_name,
    COALESCE(ps.pc_number, '') AS pc_number,
    COALESCE(ps.pc_name, '') AS pc_name,
    COALESCE(ps.district, '') AS district,
    COALESCE(ps.taluk, '') AS taluk,
    COALESCE(ps.pincode, '') AS pincode,
    
    -- Source file and page provenance
    v.source_file_id,
    COALESCE(f.name, v.source_file_name) AS source_file_name,
    v.page_number,
    v.page_id,
    v.source_record_id,
    v.is_supplement,
    
    -- Photo crop path
    ph.file_path AS photo_path,
    
    -- Audit & Timestamps
    v.created_at,
    v.updated_at,
    v.created_by,
    v.updated_by
FROM voters v
LEFT JOIN files f ON f.id = v.source_file_id
LEFT JOIN polling_stations ps ON (
    ps.id = v.polling_station_id OR 
    (ps.file_id = v.source_file_id AND ps.part_number = v.part_number)
)
LEFT JOIN photos ph ON (
    ph.voter_id = v.id AND ph.photo_type = 'voter_crop'
);
"""

DROP_VIEW_SQL = f"DROP VIEW IF EXISTS {VIEW_NAME};"


def upgrade() -> None:
    # Drop first if exists to ensure idempotent recreation
    op.execute(DROP_VIEW_SQL)
    op.execute(CREATE_VIEW_SQL)


def downgrade() -> None:
    op.execute(DROP_VIEW_SQL)
