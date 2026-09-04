# app/services/content_based.py

from typing import Optional
from app.db.data_loader import load_eligible_majors
from app.services.riasec_matcher import (
    build_major_riasec_map,
    get_riasec_match_percent,
)
from app.models.schemas import (
    MajorRecommendation,
    BestAdmissionPath,
    RecommendationResponse,
)


# ============================================================
# HÀM DÙNG CHUNG — Tái sử dụng ở Baseline 3 & 4
# ============================================================

def group_rows_by_major(rows: list[dict]) -> dict[str, list[dict]]:
    """Gom nhóm các dòng DB theo major_id"""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row["major_id"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row)
    return grouped


def build_admission_paths(rows: list[dict]) -> list[BestAdmissionPath]:
    """
    Build danh sách đường xét tuyển từ các dòng cùng 1 ngành.
    Sắp xếp theo cutoff_score giảm dần.
    """
    paths = []
    for row in rows:
        paths.append(BestAdmissionPath(
            institution_id=str(row["institution_id"]),
            institution_name=row["institution_name"],
            campus_id=str(row["campus_id"]),
            combination_code=row["combination_code"],
            student_score=0.0,     # Baseline 2 không tính điểm học sinh
            cutoff_score=float(row["cutoff_score"]),
            safety_margin=0.0,     # Baseline 2 không tính safety margin
        ))

    paths.sort(key=lambda p: p.cutoff_score, reverse=True)
    return paths


def build_major_recommendation(
    rows: list[dict],
    riasec_match_percent: float,
    final_score: float,
    primary_reason: Optional[str] = None,
) -> MajorRecommendation:
    """
    Build 1 MajorRecommendation từ các dòng cùng ngành.
    Dùng chung cho Baseline 2, 3, 4.
    """
    first = rows[0]
    paths = build_admission_paths(rows)

    return MajorRecommendation(
        major_id=str(first["major_id"]),
        major_code=first["major_code"],
        major_name_vi=first["major_name_vi"],
        major_name_en=first.get("major_name_en"),
        field_name_vi=first["field_name_vi"],
        group_name_vi=first["group_name_vi"],
        final_score=round(final_score, 4),
        riasec_match_percent=riasec_match_percent,
        best_paths=paths,
        dimensions=None,
        primary_reason=primary_reason,
    )


def build_primary_reason(
    top_code: str,
    riasec_match_percent: float,
    major_name: str,
) -> str:
    """
    Tạo câu giải thích ngắn cho học sinh.
    Baseline 2 chỉ giải thích dựa trên RIASEC.
    """
    if riasec_match_percent >= 80:
        level = "rất cao"
    elif riasec_match_percent >= 60:
        level = "cao"
    elif riasec_match_percent >= 40:
        level = "trung bình"
    else:
        level = "thấp"

    return (
        f"Ngành {major_name} có mức độ phù hợp {level} "
        f"({riasec_match_percent:.1f}%) với mã Holland {top_code} của bạn."
    )


# ============================================================
# CORE ENGINE: CONTENT-BASED FILTERING
# ============================================================

async def run_content_based(
    top_code: str,
    admission_year: int,
    top_n: int,
    province_id: Optional[str] = None,
    district_id: Optional[str] = None,
) -> RecommendationResponse:
    """
    CORE: Chạy Content-Based Filtering (Holland Only).

    Luồng xử lý:
    1. Load ngành hợp lệ từ DB (đã lọc địa lý + năm)
    2. Load RIASEC map của tất cả ngành
    3. Tính Weighted Match Score cho từng ngành
    4. Lọc bỏ ngành có match = 0 (không có dữ liệu RIASEC)
    5. Xếp hạng theo match score giảm dần
    6. Trả về top_n ngành
    """

    # Bước 1: Load ngành hợp lệ
    rows = await load_eligible_majors(
        admission_year=admission_year,
        province_id=province_id,
        district_id=district_id,
    )

    if not rows:
        return RecommendationResponse(
            baseline="content_based",
            riasec_code=top_code,
            total_candidates=0,
            results=[],
        )

    # Bước 2: Load RIASEC map (1 lần duy nhất cho toàn request)
    major_riasec_map = await build_major_riasec_map()

    # Bước 3: Gom nhóm theo ngành
    grouped = group_rows_by_major(rows)
    total_candidates = len(grouped)

    # Bước 4: Tính match score cho từng ngành
    scored_majors: list[tuple[str, float]] = []

    for major_id in grouped:
        match_percent = get_riasec_match_percent(
            top_code=top_code,
            major_id=major_id,
            major_riasec_map=major_riasec_map,
        )

        # Lọc bỏ ngành không có dữ liệu RIASEC