# app/db/queries.py

# ============================================================
# QUERY 1: Lấy tất cả ngành hợp lệ có đường xét tuyển
# Dùng cho: Tất cả 4 baseline
# Đã bỏ: major_admission_combinations (redundant)
# Lọc: is_active, năm tuyển sinh, địa lý (tuỳ chọn)
# ============================================================
GET_ELIGIBLE_MAJORS = """
    SELECT DISTINCT
        -- Thông tin ngành
        am.id                   AS major_id,
        am.major_code           AS major_code,
        am.name_vi              AS major_name_vi,
        am.name_en              AS major_name_en,

        -- Nhóm ngành & lĩnh vực
        ag.name_vi              AS group_name_vi,
        af.name_vi              AS field_name_vi,

        -- Thông tin trường (đã bổ sung name, short_name, code)
        ei.id                   AS institution_id,
        ei.name                 AS institution_name,
        ei.short_name           AS institution_short_name,
        ei.code                 AS institution_code,
        im.campus_id            AS campus_id,

        -- Tổ hợp xét tuyển & điểm chuẩn
        ac.combination_code     AS combination_code,
        ac.name_vi              AS combination_name_vi,
        acu.score               AS cutoff_score,
        acu.admission_year      AS admission_year
        
    FROM academic_majors am

    -- Nhóm ngành & lĩnh vực
    JOIN academic_groups ag         ON ag.id = am.group_id
                                    AND ag.is_active = TRUE
    JOIN academic_fields af         ON af.id = ag.field_id
                                    AND af.is_active = TRUE

    -- Trường đào tạo ngành này
    JOIN institution_majors im      ON im.major_id = am.id
                                    AND im.is_active = TRUE
                                    AND im.deleted_at IS NULL

    -- Thông tin trường
    JOIN educational_institution ei ON ei.id = im.institution_id
                                    AND ei.deleted_at IS NULL

    -- Campus
    JOIN campus c                   ON c.id = im.campus_id
                                    AND c.deleted_at IS NULL

    -- Điểm chuẩn — bỏ major_admission_combinations
    -- admission_cutoffs đã chứa đủ: major + institution + combination + year + score
    JOIN admission_cutoffs acu      ON acu.major_id = am.id
                                    AND acu.institution_id = ei.id
                                    AND acu.admission_year = $1
                                    AND acu.is_active = TRUE
                                    AND acu.deleted_at IS NULL

    -- Tổ hợp môn
    JOIN admission_combinations ac  ON ac.id = acu.combination_id
                                    AND ac.deleted_at IS NULL

    WHERE am.is_active = TRUE
    AND am.deleted_at IS NULL
"""

# ── Lọc địa lý cấp Tỉnh/Thành — nối thêm khi province_id có giá trị
GEO_FILTER_PROVINCE = """
    AND c.administrative_unit_id IN (
        SELECT id FROM administrative_units
        WHERE parent_id = $2
        AND is_active = TRUE
    )
"""

# ── Lọc địa lý cấp Quận/Huyện — nối thêm khi district_id có giá trị
GEO_FILTER_DISTRICT = """
    AND c.administrative_unit_id = $3
"""

# ── Sắp xếp dùng cho từng baseline
ORDER_RANDOM   = " ORDER BY RANDOM()"      # Baseline 1
ORDER_BY_SCORE = " ORDER BY acu.score DESC" # Baseline 2, 3, 4


# ============================================================
# QUERY 2: Lấy thông tin RIASEC của từng ngành
# Dùng cho: Baseline 2, 3, 4
# ============================================================
GET_MAJOR_RIASEC = """
    SELECT
        major_id,
        riasec_code,
        score,
        sort_order
    FROM academic_major_riasec
    WHERE deleted_at IS NULL
    ORDER BY major_id, sort_order ASC
"""

# ============================================================
# QUERY 3: Lấy các môn trong từng tổ hợp
# Dùng cho: Baseline 2, 3, 4
# ============================================================
GET_COMBINATION_SUBJECTS = """
    SELECT
        ac.combination_code,
        acs.subject_code,           -- Dùng làm key thay vì name_vi
        acs.name_vi     AS subject_name_vi,
        cs.subject_order
    FROM combination_subjects cs
    JOIN admission_combinations ac  ON ac.id = cs.combination_id
                                    AND ac.deleted_at IS NULL
    JOIN academic_subjects acs      ON acs.id = cs.subject_id
                                    AND acs.is_active = TRUE
                                    AND acs.deleted_at IS NULL
    WHERE cs.deleted_at IS NULL
    ORDER BY ac.combination_code, cs.subject_order ASC
"""

GET_ELIGIBLE_MAJORS = """
    SELECT DISTINCT
        -- Thông tin ngành
        am.id                           AS major_id,
        am.major_code                   AS major_code,
        am.name_vi                      AS major_name_vi,
        am.name_en                      AS major_name_en,

        -- Nhóm ngành & lĩnh vực
        ag.name_vi                      AS group_name_vi,
        af.name_vi                      AS field_name_vi,

        -- Thông tin trường
        ei.id                           AS institution_id,
        ei.name                         AS institution_name,
        ei.short_name                   AS institution_short_name,
        ei.code                         AS institution_code,
        im.campus_id                    AS campus_id,

        -- Địa lý campus (thêm mới)
        c.administrative_unit_id        AS campus_unit_id,

        -- Tổ hợp xét tuyển & điểm chuẩn
        ac.combination_code             AS combination_code,
        ac.name_vi                      AS combination_name_vi,
        acu.score                       AS cutoff_score,
        acu.admission_year              AS admission_year

    FROM academic_majors am
    JOIN academic_groups ag         ON ag.id = am.group_id
                                    AND ag.is_active = TRUE
    JOIN academic_fields af         ON af.id = ag.field_id
                                    AND af.is_active = TRUE
    JOIN institution_majors im      ON im.major_id = am.id
                                    AND im.is_active = TRUE
                                    AND im.deleted_at IS NULL
    JOIN educational_institution ei ON ei.id = im.institution_id
                                    AND ei.deleted_at IS NULL
    JOIN campus c                   ON c.id = im.campus_id
                                    AND c.deleted_at IS NULL
    JOIN admission_cutoffs acu      ON acu.major_id = am.id
                                    AND acu.institution_id = ei.id
                                    AND acu.admission_year = $1
                                    AND acu.is_active = TRUE
                                    AND acu.deleted_at IS NULL
    JOIN admission_combinations ac  ON ac.id = acu.combination_id
                                    AND ac.deleted_at IS NULL

    WHERE am.is_active = TRUE
    AND am.deleted_at IS NULL
"""

