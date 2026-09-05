# app/services/hybrid_fixed.py

from typing import Optional
from app.db.data_loader import load_eligible_majors
from app.services.riasec_matcher import (
    build_major_riasec_map,
    get_riasec_match_percent,
)
from app.services.subject_calculator import (
    build_combination_subject_map,
    calculate_combo_scores,
    get_best_combo_for_major,
)
from app.services.score_calculators import (
    compute_safety_score,
    compute_safety_margin,
    compute_geo_score,
    build_province_unit_ids,
)
from app.services.content_based import (
    group_rows_by_major,
)
from app.models.schemas import (
    MajorRecommendation,
    BestAdmissionPath,
    RecommendationResponse,
)

# ============================================================
# TRỌNG SỐ CỐ ĐỊNH — Baseline 3
# Tổng = 1.0
# ============================================================
ALPHA = 0.40   # RIASEC Match
BETA  = 0.25   # Subject Score
GAMMA = 0.25   # Safety Score
DELTA = 0.10   # Geo Score


# ============================================================
# HELPER: Gom nhóm combination_code theo major_id
# ============================================================

def extract_major_combinations(
    rows: list[dict],
) -> dict[str, list[str]]:
    """
    Từ data đã load, build map:
        major_id → [combination_code, ...]

    Dùng để biết ngành chấp nhận tổ hợp nào
    khi tìm tổ hợp tốt nhất cho học sinh.
    """
    major_combos: dict[str, list[str]] = {}
    for row in rows:
        major_id = str(row["major_id"])
        combo = row["combination_code"]

        if major_id not in major_combos:
            major_combos[major_id] = []

        if combo not in major_combos[major_id]:
            major_combos[major_id].append(combo)

    return major_combos


# ============================================================
# HELPER: Build BestAdmissionPath có đầy đủ thông tin
# ============================================================

def build_best_paths_hybrid(
    rows: list[dict],
    combo_results: dict,
    province_id: Optional[str],
    district_id: Optional[str],
    province_unit_ids: set[str],
) -> list[BestAdmissionPath]:
    """
    Build danh sách đường xét tuyển cho 1 ngành.
    Khác Baseline 1 & 2: có student_score và safety_margin thực tế.
    Chỉ giữ path học sinh đủ điểm (student_score >= cutoff).
    Sắp xếp theo safety_margin giảm dần.
    """
    paths = []

    for row in rows:
        combo_code = row["combination_code"]
        combo_result = combo_results.get(combo_code)

        # Bỏ qua path học sinh không có điểm tổ hợp này
        if not combo_result or not combo_result.is_valid:
            continue

        student_total = combo_result.total_score
        cutoff = float(row["cutoff_score"])
        safety_margin = compute_safety_margin(student_total, cutoff)

        # Bỏ qua path không đủ điểm chuẩn
        if safety_margin < 0:
            continue

        campus_unit_id = str(row.get("campus_unit_id", ""))
        geo_score = compute_geo_score(
            campus_unit_id=campus_unit_id,
            province_id=province_id,
            district_id=district_id,
            province_unit_ids=province_unit_ids,
        )

        paths.append(BestAdmissionPath(
            institution_id=str(row["institution_id"]),
            institution_name=row["institution_name"],
            campus_id=str(row["campus_id"]),
            combination_code=combo_code,
            student_score=student_total,
            cutoff_score=cutoff,
            safety_margin=safety_margin,
        ))

    # Sắp xếp theo safety_margin giảm dần — trường an toàn nhất lên đầu
    paths.sort(key=lambda p: p.safety_margin, reverse=True)
    return paths


# ============================================================
# HELPER: Build primary_reason cho Baseline 3
# ============================================================

def build_primary_reason_hybrid(
    top_code: str,
    riasec_percent: float,
    best_combo: str,
    student_total: float,
    cutoff: float,
    final_score: float,
) -> str:
    """Câu giải thích tổng hợp 4 yếu tố cho học sinh"""

    safety_margin = student_total - cutoff

    if final_score >= 0.75:
        overall = "rất phù hợp"
    elif final_score >= 0.55:
        overall = "phù hợp"
    else:
        overall = "có thể cân nhắc"

    return (
        f"Ngành này {overall} với bạn — "
        f"khớp Holland {riasec_percent:.1f}% (mã {top_code}), "
        f"tổ hợp tốt nhất {best_combo} với tổng điểm {student_total:.1f} "
        f"(dư {safety_margin:.1f}đ so với điểm chuẩn)."
    )


# ============================================================
# CORE ENGINE: HYBRID FIXED WEIGHTS
# ============================================================

async def run_hybrid_fixed(
    top_code: str,
    student_scores: dict[str, float],
    admission_year: int,
    top_n: int,
    province_id: Optional[str] = None,
    district_id: Optional[str] = None,
) -> RecommendationResponse:
    """
    CORE: Chạy Hybrid Fixed Weights.

    Luồng xử lý:
    1. Load ngành hợp lệ + RIASEC map + combo map song song
    2. Pre-compute province_unit_ids nếu có lọc địa lý
    3. Tính điểm học sinh theo từng tổ hợp
    4. Với mỗi ngành:
       a. Tìm tổ hợp tốt nhất
       b. Tính 4 thành phần điểm
       c. Tính FinalScore = α·RIASEC + β·Subject + γ·Safety + δ·Geo
       d. Lọc bỏ ngành không có đường xét tuyển hợp lệ
    5. Xếp hạng theo FinalScore giảm dần
    6. Trả về top_n ngành
    """

    # Bước 1: Load data song song
    import asyncio
    rows, major_riasec_map, combo_map = await asyncio.gather(
        load_eligible_majors(
            admission_year=admission_year,
            province_id=province_id,
            district_id=district_id,
        ),
        build_major_riasec_map(),
        build_combination_subject_map(),
    )

    if not rows:
        return RecommendationResponse(
            baseline="hybrid_fixed",
            riasec_code=top_code,
            total_candidates=0,
            results=[],
        )

    # Bước 2: Pre-compute province_unit_ids
    province_unit_ids: set[str] = set()
    if province_id:
        province_unit_ids = await build_province_unit_ids(province_id)

    # Bước 3: Tính điểm học sinh theo từng tổ hợp (1 lần cho toàn request)
    combo_results = calculate_combo_scores(student_scores, combo_map)

    # Gom nhóm data theo ngành
    grouped = group_rows_by_major(rows)
    major_combinations = extract_major_combinations(rows)
    total_candidates = len(grouped)

    # Bước 4: Tính FinalScore cho từng ngành
    scored_majors: list[tuple[str, float, float, str, float, float]] = []
    # (major_id, final_score, riasec_percent, best_combo, best_total, best_cutoff)

    for major_id, major_rows in grouped.items():

        # 4a. RIASEC Score
        riasec_percent = get_riasec_match_percent(
            top_code=top_code,
            major_id=major_id,
            major_riasec_map=major_riasec_map,
        )
        riasec_score = riasec_percent / 100

        # 4b. Subject Score — tìm tổ hợp tốt nhất
        major_combos = major_combinations.get(major_id, [])
        best_combo, best_total, subject_score = get_best_combo_for_major(
            major_combinations=major_combos,
            combo_results=combo_results,
        )

        # Bỏ qua ngành không có tổ hợp hợp lệ
        if not best_combo:
            continue

        # 4c. Safety Score — dùng tổ hợp tốt nhất
        # Tìm cutoff của tổ hợp tốt nhất tại trường tốt nhất
        best_cutoff = 0.0
        for row in major_rows:
            if row["combination_code"] == best_combo:
                cutoff = float(row["cutoff_score"])
                margin = best_total - cutoff
                if margin >= 0 and cutoff > best_cutoff:
                    best_cutoff = cutoff

        # Bỏ qua ngành không đủ điểm chuẩn ở bất kỳ trường nào
        if best_cutoff == 0.0:
            continue

        safety_score = compute_safety_score(best_total, best_cutoff)

        # 4d. Geo Score — dùng campus của trường có cutoff tốt nhất
        geo_score = 0.0
        for row in major_rows:
            if (
                row["combination_code"] == best_combo
                and float(row["cutoff_score"]) == best_cutoff
            ):
                campus_unit_id = str(row.get("campus_unit_id", ""))
                geo_score = compute_geo_score(
                    campus_unit_id=campus_unit_id,
                    province_id=province_id,
                    district_id=district_id,
                    province_unit_ids=province_unit_ids,
                )
                break

        # 4e. FinalScore tổng hợp
        final_score = (
            ALPHA * riasec_score +
            BETA  * subject_score +
            GAMMA * safety_score +
            DELTA * geo_score
        )

        scored_majors.append((
            major_id,
            final_score,
            riasec_percent,
            best_combo,
            best_total,
            best_cutoff,
        ))

    # Bước 5: Xếp hạng theo FinalScore giảm dần
    scored_majors.sort(key=lambda x: x[1], reverse=True)

    # Bước 6: Build kết quả top_n
    results: list[MajorRecommendation] = []

    for (
        major_id,
        final_score,
        riasec_percent,
        best_combo,
        best_total,
        best_cutoff,
    ) in scored_majors[:top_n]:

        major_rows = grouped[major_id]
        first = major_rows[0]

        # Build paths chỉ gồm path đủ điểm
        best_paths = build_best_paths_hybrid(
            rows=major_rows,
            combo_results=combo_results,
            province_id=province_id,
            district_id=district_id,
            province_unit_ids=province_unit_ids,
        )

        reason = build_primary_reason_hybrid(
            top_code=top_code,
            riasec_percent=riasec_percent,
            best_combo=best_combo,
            student_total=best_total,
            cutoff=best_cutoff,
            final_score=final_score,
        )

        results.append(MajorRecommendation(
            major_id=str(first["major_id"]),
            major_code=first["major_code"],
            major_name_vi=first["major_name_vi"],
            major_name_en=first.get("major_name_en"),
            field_name_vi=first["field_name_vi"],
            group_name_vi=first["group_name_vi"],
            final_score=round(final_score, 4),
            riasec_match_percent=riasec_percent,
            best_paths=best_paths,
            dimensions=None,
            primary_reason=reason,
        ))

    return RecommendationResponse(
        baseline="hybrid_fixed",
        riasec_code=top_code,
        total_candidates=total_candidates,
        results=results,
    )