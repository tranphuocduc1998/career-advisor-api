# app/services/proposed_method.py
# Baseline 4: Hybrid trọng số tối ưu + Explainability

import asyncio
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
from app.services.explainability import explain_recommendation
from app.services.grid_search import load_best_weights
from app.services.hybrid_fixed import (
    group_rows_by_major,
    extract_major_combinations,
    build_best_paths_hybrid,
)
from app.models.schemas import (
    MajorRecommendation,
    RecommendationResponse,
)


# ============================================================
# LOAD TRỌNG SỐ TỐI ƯU
# ============================================================

def get_optimal_weights() -> dict[str, float]:
    """
    Load trọng số tối ưu từ Grid Search.
    Fallback về trọng số mặc định nếu chưa có file.
    """
    try:
        best = load_best_weights()
        return {
            "alpha": best["alpha"],   # RIASEC
            "beta":  best["beta"],    # Subject
            "gamma": best["gamma"],   # Safety
            "delta": best["delta"],   # Geo
            "k":     best["k"],       # K tối ưu
        }
    except FileNotFoundError:
        # Fallback — dùng kết quả Grid Search đã biết
        return {
            "alpha": 0.7,
            "beta":  0.1,
            "gamma": 0.1,
            "delta": 0.1,
            "k":     3,
        }


# ============================================================
# CORE ENGINE: PROPOSED METHOD
# ============================================================

async def run_proposed_method(
    top_code: str,
    student_scores: dict[str, float],
    admission_year: int,
    top_n: int,
    province_id: Optional[str] = None,
    district_id: Optional[str] = None,
) -> RecommendationResponse:
    """
    CORE: Chạy Proposed Method.

    Khác Baseline 3:
        1. Trọng số đọc từ Grid Search result
        2. Mỗi ngành có ExplanationResult đầy đủ
        3. Top N dùng K tối ưu làm mặc định

    Luồng xử lý:
        1. Load trọng số tối ưu
        2. Load data DB song song
        3. Pre-compute province_unit_ids nếu có địa lý
        4. Tính điểm tổ hợp học sinh
        5. Với mỗi ngành: tính 4 chiều + FinalScore + Explanation
        6. Xếp hạng và trả về top_n
    """

    # Bước 1: Load trọng số tối ưu
    weights = get_optimal_weights()
    alpha = weights["alpha"]
    beta  = weights["beta"]
    gamma = weights["gamma"]
    delta = weights["delta"]

    # Bước 2: Load data song song
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
            baseline="proposed",
            riasec_code=top_code,
            total_candidates=0,
            results=[],
        )

    # Bước 3: Pre-compute province_unit_ids
    province_unit_ids: set[str] = set()
    if province_id:
        province_unit_ids = await build_province_unit_ids(province_id)

    # Bước 4: Tính điểm tổ hợp học sinh
    combo_results = calculate_combo_scores(student_scores, combo_map)

    # Gom nhóm data
    grouped = group_rows_by_major(rows)
    major_combinations = extract_major_combinations(rows)
    total_candidates = len(grouped)

    # Bước 5: Tính FinalScore + Explanation cho từng ngành
    scored_majors: list[tuple[str, float, dict]] = []
    # (major_id, final_score, score_components)

    for major_id, major_rows in grouped.items():

        # ── RIASEC Score ──
        riasec_percent = get_riasec_match_percent(
            top_code=top_code,
            major_id=major_id,
            major_riasec_map=major_riasec_map,
        )
        riasec_score = riasec_percent / 100

        # ── Subject Score ──
        major_combos = major_combinations.get(major_id, [])
        best_combo, best_total, subject_score = get_best_combo_for_major(
            major_combinations=major_combos,
            combo_results=combo_results,
        )

        if not best_combo:
            continue

        # ── Safety Score ──
        best_cutoff = 0.0
        for row in major_rows:
            if row["combination_code"] == best_combo:
                cutoff = float(row["cutoff_score"])
                if best_total >= cutoff and cutoff > best_cutoff:
                    best_cutoff = cutoff

        if best_cutoff == 0.0:
            continue

        safety_score = compute_safety_score(best_total, best_cutoff)

        # ── Geo Score ──
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

        # ── FinalScore với trọng số tối ưu ──
        final_score = (
            alpha * riasec_score +
            beta  * subject_score +
            gamma * safety_score +
            delta * geo_score
        )

        scored_majors.append((major_id, final_score, {
            "riasec_score":   riasec_score,
            "riasec_percent": riasec_percent,
            "subject_score":  subject_score,
            "safety_score":   safety_score,
            "geo_score":      geo_score,
            "best_combo":     best_combo,
            "best_total":     best_total,
            "best_cutoff":    best_cutoff,
        }))

    # Bước 6: Xếp hạng theo FinalScore
    scored_majors.sort(key=lambda x: x[1], reverse=True)

    # Bước 7: Build kết quả top_n với Explainability
    results: list[MajorRecommendation] = []

    for major_id, final_score, components in scored_majors[:top_n]:
        major_rows = grouped[major_id]
        first = major_rows[0]

        # Build explanation
        explanation = explain_recommendation(
            top_code=top_code,
            major_name=first["major_name_vi"],
            riasec_score=components["riasec_score"],
            subject_score=components["subject_score"],
            safety_score=components["safety_score"],
            geo_score=components["geo_score"],
            best_combo=components["best_combo"],
            student_total=components["best_total"],
            cutoff=components["best_cutoff"],
            final_score=final_score,
            weights={
                "alpha": alpha,
                "beta":  beta,
                "gamma": gamma,
                "delta": delta,
            },
        )

        # Build admission paths
        best_paths = build_best_paths_hybrid(
            rows=major_rows,
            combo_results=combo_results,
            province_id=province_id,
            district_id=district_id,
            province_unit_ids=province_unit_ids,
        )

        results.append(MajorRecommendation(
            major_id=str(first["major_id"]),
            major_code=first["major_code"],
            major_name_vi=first["major_name_vi"],
            major_name_en=first.get("major_name_en"),
            field_name_vi=first["field_name_vi"],
            group_name_vi=first["group_name_vi"],
            final_score=round(final_score, 4),
            riasec_match_percent=components["riasec_percent"],
            best_paths=best_paths,
            dimensions=explanation.dimensions,
            primary_reason=explanation.primary_reason,
        ))

    return RecommendationResponse(
        baseline="proposed",
        riasec_code=top_code,
        total_candidates=total_candidates,
        results=results,
    )