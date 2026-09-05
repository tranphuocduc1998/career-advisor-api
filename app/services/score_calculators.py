# app/services/score_calculators.py
# Tính SafetyScore và GeoScore
# Dùng chung cho Baseline 3 và 4


# ============================================================
# SAFETY SCORE
# ============================================================

# Biên an toàn tối đa — dư 5 điểm = an toàn tuyệt đối
# Cơ sở: thực tế tuyển sinh VN, dư 3-5 điểm là rất an toàn
SAFETY_RANGE = 5.0


def compute_safety_score(
    student_total: float,
    cutoff_score: float,
) -> float:
    """
    Tính SafetyScore — mức độ an toàn khi đăng ký ngành này.

    Công thức:
        safety_margin = student_total - cutoff_score
        SafetyScore   = clip(safety_margin / SAFETY_RANGE, 0, 1)

    Ý nghĩa:
        safety_margin <= 0  → không đủ điểm    → SafetyScore = 0.0
        safety_margin = 2.5 → dư nửa range     → SafetyScore = 0.5
        safety_margin >= 5  → rất an toàn      → SafetyScore = 1.0

    Ví dụ:
        student_total=24.5, cutoff=22.0 → margin=2.5 → score=0.50
        student_total=24.5, cutoff=26.0 → margin=-1.5 → score=0.0
    """
    safety_margin = student_total - cutoff_score

    if safety_margin <= 0:
        return 0.0

    return round(min(safety_margin / SAFETY_RANGE, 1.0), 4)


def compute_safety_margin(
    student_total: float,
    cutoff_score: float,
) -> float:
    """
    Trả về safety_margin thô (có thể âm).
    Dùng để hiển thị UI — không dùng trong công thức tính điểm.
    """
    return round(student_total - cutoff_score, 2)


# ============================================================
# GEO SCORE
# ============================================================

GEO_SCORE_MAP = {
    "district_match": 1.00,  # Khớp cả tỉnh lẫn quận/huyện
    "province_match": 0.50,  # Chỉ khớp tỉnh/thành
    "no_filter":      0.00,  # Học sinh không chọn địa lý
    "no_match":       0.00,  # Không khớp địa lý
}


def compute_geo_score(
    campus_unit_id: str,
    province_id: str | None,
    district_id: str | None,
    province_unit_ids: set[str],
) -> float:
    """
    Tính GeoScore — mức độ khớp địa lý giữa campus và mong muốn học sinh.

    Tham số:
        campus_unit_id   : administrative_unit_id của campus (từ DB)
        province_id      : ID tỉnh học sinh chọn (None nếu không chọn)
        district_id      : ID quận/huyện học sinh chọn (None nếu không chọn)
        province_unit_ids: set các unit_id thuộc tỉnh đã chọn

    Logic:
        Không chọn địa lý              → 0.0
        Khớp quận/huyện chính xác      → 1.0
        Campus thuộc tỉnh đã chọn      → 0.5
        Không khớp                     → 0.0

    Ví dụ:
        Học sinh chọn Hà Nội + Cầu Giấy
        Campus A ở Cầu Giấy  → 1.0
        Campus B ở Đống Đa   → 0.5
        Campus C ở TP.HCM    → 0.0
    """
    if not province_id:
        return GEO_SCORE_MAP["no_filter"]

    if district_id and campus_unit_id == district_id:
        return GEO_SCORE_MAP["district_match"]

    if campus_unit_id in province_unit_ids:
        return GEO_SCORE_MAP["province_match"]

    return GEO_SCORE_MAP["no_match"]


# ============================================================
# HELPER: Build province_unit_ids từ data đã load
# ============================================================

async def build_province_unit_ids(
    province_id: str,
) -> set[str]:
    """
    Query DB lấy tất cả administrative_unit_id
    là con của tỉnh province_id.

    Dùng bảng administrative_units với quan hệ parent_id.
    Gọi 1 lần duy nhất mỗi request khi học sinh có chọn địa lý.
    """
    from app.db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text AS unit_id
            FROM administrative_units
            WHERE parent_id = $1::uuid
            AND is_active = TRUE
            """,
            province_id,
        )
    return {row["unit_id"] for row in rows}