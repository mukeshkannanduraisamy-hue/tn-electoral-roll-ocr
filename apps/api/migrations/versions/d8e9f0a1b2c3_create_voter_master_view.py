"""create electoral roll views (Standard Professional Names with Join IDs)

Revision ID: d8e9f0a1b2c3
Revises: 7743375bcf7b
Create Date: 2026-08-17 10:00:00.000000

Creates the 4 standard professional views for the electoral roll system with Join IDs:
1. `view_part_details` (Table 1: includes polling_station_id, file_id)
2. `view_elector_counts` (Table 2: includes polling_station_id, file_id)
3. `view_voters_list` (Table 3: includes voter_id, polling_station_id, file_id)
4. `view_voter_master` (Unified Master: includes voter_id, polling_station_id, file_id)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, Sequence[str], None] = '7743375bcf7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_VIEWS_SQL = """
-- ==============================================================================
-- 1. VIEW 1: view_part_details (Table 1)
-- ==============================================================================
DROP VIEW IF EXISTS public.view_part_details CASCADE;
CREATE VIEW public.view_part_details AS
SELECT 
    COALESCE(ps.ac_number, '58') AS "சட்டமன்ற_தொகுதி_எண்",
    COALESCE(ps.ac_name, 'பென்னாகரம்') AS "சட்டமன்ற_தொகுதி_பெயர்",
    COALESCE(ps.payload->>'ac_reservation', 'பொது') AS "சட்டமன்ற_ஒதுக்கீடு",
    ps.part_number AS "பாகம்_எண்",
    COALESCE(ps.pc_number, '10') AS "நாடாளுமன்ற_தொகுதி_எண்",
    COALESCE(ps.pc_name, 'தர்மபுரி') AS "நாடாளுமன்ற_பெயர்",
    COALESCE(ps.payload->>'pc_reservation', 'பொது') AS "நாடாளுமன்ற_ஒதுக்கீடு",
    COALESCE(ps.payload->>'revision_year', '2026') AS "திருத்தப்படும்_ஆண்டு",
    COALESCE(ps.section_details, '') AS "பிரிவு_விவரம்",
    COALESCE(ps.payload->>'main_town', '') AS "முக்கிய_நகரம்_கிராமம்",
    COALESCE(ps.payload->>'ward', '') AS "வார்டு",
    COALESCE(ps.payload->>'panchayat', '') AS "பஞ்சாயத்து",
    COALESCE(ps.taluk, 'பென்னாகரம்') AS "வட்டம்",
    COALESCE(ps.district, 'தர்மபுரி') AS "மாவட்டம்",
    COALESCE(ps.pincode, '') AS "அஞ்சல்_குறியீட்டு_எண்",
    
    -- Join / Provenance IDs
    ps.id AS polling_station_id,
    ps.file_id AS file_id,
    COALESCE(f.name, '') AS source_file_name,
    ps.created_at
FROM public.polling_stations ps
LEFT JOIN public.files f ON f.id = ps.file_id;

-- ==============================================================================
-- 2. VIEW 2: view_elector_counts (Table 2)
-- ==============================================================================
DROP VIEW IF EXISTS public.view_elector_counts CASCADE;
CREATE VIEW public.view_elector_counts AS
SELECT 
    ps.part_number AS "பாகம்_எண்",
    COALESCE(ps.serial_start, 1) AS "தொடங்கும்_வரிசை_எண்",
    COALESCE(ps.serial_end, ps.total_electors, 0) AS "முடியும்_வரிசை_எண்",
    COALESCE(ps.male_electors, (ps.payload->'counts'->>'male')::int, 0) AS "ஆண்",
    COALESCE(ps.female_electors, (ps.payload->'counts'->>'female')::int, 0) AS "பெண்",
    COALESCE(ps.third_gender_electors, (ps.payload->'counts'->>'third_gender')::int, 0) AS "மூன்றாம்_பாலினம்",
    COALESCE(ps.total_electors, (ps.payload->'counts'->>'total')::int, 0) AS "மொத்தம்",
    
    -- Join / Provenance IDs
    ps.id AS polling_station_id,
    ps.file_id AS file_id,
    COALESCE(f.name, '') AS source_file_name,
    ps.created_at
FROM public.polling_stations ps
LEFT JOIN public.files f ON f.id = ps.file_id;

-- ==============================================================================
-- 3. VIEW 3: view_voters_list (Table 3)
-- ==============================================================================
DROP VIEW IF EXISTS public.view_voters_list CASCADE;
CREATE VIEW public.view_voters_list AS
SELECT 
    v.serial AS "வாக்காளர்_sno",
    v.epic AS "epic_id",
    v.name AS "பெயர்",
    CASE 
        WHEN LOWER(v.relation_type) IN ('husband', 'கணவர்') THEN 'கணவர் பெயர்'
        WHEN LOWER(v.relation_type) IN ('mother', 'தாய்') THEN 'தாய் பெயர்'
        WHEN LOWER(v.relation_type) IN ('other', 'guardian', 'இதர', 'காப்பாளர்') THEN 'காப்பாளர் பெயர்'
        ELSE 'தந்தை பெயர்'
    END AS "உறவு_முறை",
    v.relation_name AS "தந்தை_கணவர்_பெயர்",
    v.house_number AS "வீட்டு_எண்",
    v.age AS "வயது",
    CASE 
        WHEN LOWER(v.gender) IN ('male', 'm', 'ஆண்') THEN 'ஆண்'
        WHEN LOWER(v.gender) IN ('female', 'f', 'பெண்') THEN 'பெண்'
        WHEN LOWER(v.gender) IN ('third_gender', 'third gender', 'transgender', 'மூன்றாம் பாலினம்') THEN 'மூன்றாம் பாலினம்'
        ELSE v.gender 
    END AS "பாலினம்",
    TRIM(CONCAT(
        COALESCE(ps.ac_number, '58'), '-', COALESCE(ps.ac_name, 'பென்னாகரம்'), 
        ' பிரிவு எண் மற்றும் பெயர் ', 
        COALESCE(v.section_name, ps.section_details, '')
    )) AS "பிரிவு_தலைப்பு",
    v.part_number AS "பாகம்_எண்",
    
    -- Join / Provenance IDs
    v.id AS voter_id,
    COALESCE(v.polling_station_id, ps.id) AS polling_station_id,
    COALESCE(v.source_file_id, ps.file_id) AS file_id,
    v.is_deleted,
    v.deletion_reason,
    COALESCE(f.name, v.source_file_name) AS source_file_name,
    v.page_number,
    v.created_at
FROM public.voters v
LEFT JOIN public.files f ON f.id = v.source_file_id
LEFT JOIN public.polling_stations ps ON (
    ps.id = v.polling_station_id OR 
    (ps.file_id = v.source_file_id AND ps.part_number = v.part_number)
);

-- ==============================================================================
-- 4. MASTER VIEW: view_voter_master (Unified Flat Table - No Repeated Columns)
-- ==============================================================================
DROP VIEW IF EXISTS public.view_voter_master CASCADE;
CREATE VIEW public.view_voter_master AS
SELECT 
    -- 1. Voter Details (Table 3)
    v.serial AS "வாக்காளர்_sno",
    v.epic AS "epic_id",
    v.name AS "பெயர்",
    CASE 
        WHEN LOWER(v.relation_type) IN ('husband', 'கணவர்') THEN 'கணவர் பெயர்'
        WHEN LOWER(v.relation_type) IN ('mother', 'தாய்') THEN 'தாய் பெயர்'
        WHEN LOWER(v.relation_type) IN ('other', 'guardian', 'இதர', 'காப்பாளர்') THEN 'காப்பாளர் பெயர்'
        ELSE 'தந்தை பெயர்'
    END AS "உறவு_முறை",
    v.relation_name AS "தந்தை_கணவர்_பெயர்",
    v.house_number AS "வீட்டு_எண்",
    v.age AS "வயது",
    CASE 
        WHEN LOWER(v.gender) IN ('male', 'm', 'ஆண்') THEN 'ஆண்'
        WHEN LOWER(v.gender) IN ('female', 'f', 'பெண்') THEN 'பெண்'
        WHEN LOWER(v.gender) IN ('third_gender', 'third gender', 'transgender', 'மூன்றாம் பாலினம்') THEN 'மூன்றாம் பாலினம்'
        ELSE v.gender 
    END AS "பாலினம்",

    -- 2. Location & Section (Table 1 Area)
    TRIM(CONCAT(
        COALESCE(ps.ac_number, '58'), '-', COALESCE(ps.ac_name, 'பென்னாகரம்'), 
        ' பிரிவு எண் மற்றும் பெயர் ', 
        COALESCE(v.section_name, ps.section_details, '')
    )) AS "பிரிவு_தலைப்பு",
    COALESCE(ps.section_details, v.section_name, '') AS "பிரிவு_விவரம்",
    COALESCE(ps.payload->>'main_town', '') AS "முக்கிய_நகரம்_கிராமம்",
    COALESCE(ps.payload->>'ward', '') AS "வார்டு",
    COALESCE(ps.payload->>'panchayat', '') AS "பஞ்சாயத்து",
    COALESCE(ps.taluk, 'பென்னாகரம்') AS "வட்டம்",
    COALESCE(ps.district, 'தர்மபுரி') AS "மாவட்டம்",
    COALESCE(ps.pincode, '') AS "அஞ்சல்_குறியீட்டு_எண்",

    -- 3. Constituency & Part Identity (Table 1 Identity)
    COALESCE(v.part_number, ps.part_number, '') AS "பாகம்_எண்",
    COALESCE(ps.ac_number, '58') AS "சட்டமன்ற_தொகுதி_எண்",
    COALESCE(ps.ac_name, 'பென்னாகரம்') AS "சட்டமன்ற_தொகுதி_பெயர்",
    COALESCE(ps.payload->>'ac_reservation', 'பொது') AS "சட்டமன்ற_ஒதுக்கீடு",
    COALESCE(ps.pc_number, '10') AS "நாடாளுமன்ற_தொகுதி_எண்",
    COALESCE(ps.pc_name, 'தர்மபுரி') AS "நாடாளுமன்ற_பெயர்",
    COALESCE(ps.payload->>'pc_reservation', 'பொது') AS "நாடாளுமன்ற_ஒதுக்கீடு",
    COALESCE(ps.payload->>'revision_year', '2026') AS "திருத்தப்படும்_ஆண்டு",

    -- 4. Part Summary Counts (Table 2)
    COALESCE(ps.serial_start, 1) AS "தொடங்கும்_வரிசை_எண்",
    COALESCE(ps.serial_end, ps.total_electors, 0) AS "முடியும்_வரிசை_எண்",
    COALESCE(ps.male_electors, (ps.payload->'counts'->>'male')::int, 0) AS "ஆண்_வாக்காளர்கள்",
    COALESCE(ps.female_electors, (ps.payload->'counts'->>'female')::int, 0) AS "பெண்_வாக்காளர்கள்",
    COALESCE(ps.third_gender_electors, (ps.payload->'counts'->>'third_gender')::int, 0) AS "மூன்றாம்_பாலினம்",
    COALESCE(ps.total_electors, (ps.payload->'counts'->>'total')::int, 0) AS "மொத்த_வாக்காளர்கள்",

    -- 5. Join / Provenance IDs
    v.id AS voter_id,
    COALESCE(v.polling_station_id, ps.id) AS polling_station_id,
    COALESCE(v.source_file_id, ps.file_id) AS file_id,
    v.is_deleted,
    v.deletion_reason,
    COALESCE(f.name, v.source_file_name) AS source_file_name,
    v.page_number,
    v.created_at
FROM public.voters v
LEFT JOIN public.files f ON f.id = v.source_file_id
LEFT JOIN public.polling_stations ps ON (
    ps.id = v.polling_station_id OR 
    (ps.file_id = v.source_file_id AND ps.part_number = v.part_number)
);
"""

DROP_VIEWS_SQL = """
DROP VIEW IF EXISTS public.view_part_details CASCADE;
DROP VIEW IF EXISTS public.view_elector_counts CASCADE;
DROP VIEW IF EXISTS public.view_voters_list CASCADE;
DROP VIEW IF EXISTS public.view_voter_master CASCADE;
"""


def upgrade() -> None:
    op.execute(CREATE_VIEWS_SQL)


def downgrade() -> None:
    op.execute(DROP_VIEWS_SQL)
