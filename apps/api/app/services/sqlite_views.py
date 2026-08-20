from sqlalchemy import create_engine, text, inspect
from app.config import settings

def ensure_sqlite_views(engine):
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE VIEW IF NOT EXISTS view_part_details AS
        SELECT 
            COALESCE(ps.ac_number, '58') AS "சட்டமன்ற_தொகுதி_எண்",
            COALESCE(ps.ac_name, 'பென்னாகரம்') AS "சட்டமன்ற_தொகுதி_பெயர்",
            COALESCE(json_extract(ps.payload, '$.ac_reservation'), 'பொது') AS "சட்டமன்ற_ஒதுக்கீடு",
            ps.part_number AS "பாகம்_எண்",
            COALESCE(ps.pc_number, '10') AS "நாடாளுமன்ற_தொகுதி_எண்",
            COALESCE(ps.pc_name, 'தர்மபுரி') AS "நாடாளுமன்ற_பெயர்",
            COALESCE(json_extract(ps.payload, '$.pc_reservation'), 'பொது') AS "நாடாளுமன்ற_ஒதுக்கீடு",
            COALESCE(json_extract(ps.payload, '$.revision_year'), '2026') AS "திருத்தப்படும்_ஆண்டு",
            COALESCE(ps.section_details, '') AS "பிரிவு_விவரம்",
            COALESCE(json_extract(ps.payload, '$.main_town'), '') AS "முக்கிய_நகரம்_கிராமம்",
            COALESCE(json_extract(ps.payload, '$.ward'), '') AS "வார்டு",
            COALESCE(json_extract(ps.payload, '$.panchayat'), '') AS "பஞ்சாயத்து",
            COALESCE(ps.taluk, 'பென்னாகரம்') AS "வட்டம்",
            COALESCE(ps.district, 'தர்மபுரி') AS "மாவட்டம்",
            COALESCE(ps.pincode, '') AS "அஞ்சல்_குறியீட்டு_எண்",
            ps.id AS part_details_id,
            COALESCE(f.name, '') AS source_file_name,
            ps.created_at
        FROM polling_stations ps
        LEFT JOIN files f ON f.id = ps.file_id;
        """))

        conn.execute(text("""
        CREATE VIEW IF NOT EXISTS view_elector_counts AS
        SELECT 
            ps.part_number AS "பாகம்_எண்",
            COALESCE(ps.serial_start, 1) AS "தொடங்கும்_வரிசை_எண்",
            COALESCE(ps.serial_end, ps.total_electors, 0) AS "முடியும்_வரிசை_எண்",
            COALESCE(ps.male_electors, CAST(json_extract(ps.payload, '$.counts.male') AS INTEGER), 0) AS "ஆண்",
            COALESCE(ps.female_electors, CAST(json_extract(ps.payload, '$.counts.female') AS INTEGER), 0) AS "பெண்",
            COALESCE(ps.third_gender_electors, CAST(json_extract(ps.payload, '$.counts.third_gender') AS INTEGER), 0) AS "மூன்றாம்_பாலினம்",
            COALESCE(ps.total_electors, CAST(json_extract(ps.payload, '$.counts.total') AS INTEGER), 0) AS "மொத்தம்",
            ps.id AS elector_counts_id,
            ps.id AS part_details_id,
            COALESCE(f.name, '') AS source_file_name,
            ps.created_at
        FROM polling_stations ps
        LEFT JOIN files f ON f.id = ps.file_id;
        """))

        conn.execute(text("""
        CREATE VIEW IF NOT EXISTS view_voters_list AS
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
            TRIM(
                COALESCE(ps.ac_number, '58') || '-' || COALESCE(ps.ac_name, 'பென்னாகரம்') || 
                ' பிரிவு எண் மற்றும் பெயர் ' || 
                COALESCE(v.section_name, ps.section_details, '')
            ) AS "பிரிவு_தலைப்பு",
            v.part_number AS "பாகம்_எண்",
            v.id AS voters_list_id,
            COALESCE(v.polling_station_id, ps.id) AS part_details_id,
            COALESCE(v.polling_station_id, ps.id) AS elector_counts_id,
            v.is_deleted,
            v.deletion_reason,
            COALESCE(f.name, v.source_file_name) AS source_file_name,
            v.page_number,
            v.created_at
        FROM voters v
        LEFT JOIN files f ON f.id = v.source_file_id
        LEFT JOIN polling_stations ps ON (
            ps.id = v.polling_station_id OR 
            (ps.file_id = v.source_file_id AND ps.part_number = v.part_number)
        );
        """))

if __name__ == "__main__":
    engine = create_engine("sqlite:///D:/OCR/data/ocr.sqlite")
    ensure_sqlite_views(engine)
    insp = inspect(engine)
    print("Tables:", len(insp.get_table_names()))
    print("Views:", len(insp.get_view_names()), insp.get_view_names())
