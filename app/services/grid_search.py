# app/services/grid_search.py
# Grid Search tìm đồng thời trọng số tối ưu và K tối ưu
# Chạy 1 lần, lưu kết quả vào JSON

import json
import asyncio
from pathlib import Path
from itertools import product
from dataclasses import dataclass, asdict

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
    compute_geo_score,
)
from app.services.content_based import group_rows_by_major
from app.services.ground_truth import load_ground_truth
from app.services.evaluator import (
    evaluate_single,
    evaluate_dataset,
    find_best_k,
    AggregateEvalResult,
)

# ============================================================
# CONSTANTS
# ============================================================

GRID_RESULT_PATH = Path("app/data/grid_search_result.json")
ADMISSION_YEAR = 2026

# Lưới tìm kiếm trọng số — tổng = 1.0
# Bước 0.1 → mỗi trọng số từ 0.1 đến 0.7
WEIGHT_GRID = [round(w, 1) for w in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]]

# Lưới K cần thử
K_GRID = [3, 5, 7, 10]

# Số kết quả tốt nhất lưu lại để phân tích
TOP_N_RESULTS = 10


# ============================================================
# KIỂU DỮ LIỆU
# ============================================================

@dataclass
class WeightConfig:
    """1 bộ trọng số cần thử"""
    alpha: float    # RIASEC
    beta: float     # Subject
    gamma: float    # Safety
    delta: float    # Geo


@dataclass
class GridSearchResult:
    """Kết quả 1 tổ hợp (weights, K)"""
    alpha: float
    beta: float
    gamma: float
    delta: float
    k: int
    mean_precision: float
    mean_ndcg: float
    mean_combined: float
    num_profiles: int


# ============================================================
# BƯỚC 1: Sinh lưới trọng số hợp lệ
# ============================================================

def generate_weight_grid() -> list[WeightConfig]:
    """
    Sinh tất cả tổ hợp (α, β, γ, δ) hợp lệ.

    Điều kiện:
        α + β + γ + δ = 1.0
        Mỗi trọng số ∈ WEIGHT_GRID (0.1 → 0.7)
        α >= β >= δ  (RIASEC quan trọng nhất, Geo ít nhất)

    Ràng buộc thứ tự giúp giảm không gian tìm kiếm
    từ ~2000 xuống còn ~200 tổ hợp hợp lệ.
    """
    configs = []

    for alpha, beta, gamma, delta in product(WEIGHT_GRID, repeat=4):
        # Tổng phải = 1.0
        if abs(alpha + beta + gamma + delta - 1.0) > 0.001:
            continue

        # Ràng buộc thứ tự ưu tiên
        if alpha < beta:
            continue
        if delta > beta:
            continue

        configs.append(WeightConfig(alpha, beta, gamma, delta))

    return configs


# ============================================================
# BƯỚC 2: Tính FinalScore cho 1 hồ sơ với 1 bộ trọng số
# ============================================================

def score_majors_for_profile(
    profile: dict,
    grouped: dict,
    major_riasec_map: dict,
    combo_map: dict,
    weights: WeightConfig,
) -> list[str]:
    """
    Tính FinalScore cho tất cả ngành với 1 hồ sơ + 1 bộ trọng số.
    Trả về list[major_code] đã sắp xếp theo FinalScore giảm dần.

    Không dùng địa lý trong Grid Search —
    vì ground truth không có thông tin địa lý.
    """
    top_code = profile["top_code"]
    student_scores = profile["scores"]

    # Tính điểm tổ hợp 1 lần
    combo_results = calculate_combo_scores(student_scores, combo_map)

    scored: list[tuple[str, float]] = []

    for major_id, rows in grouped.items():
        # RIASEC Score
        riasec_percent = get_riasec_match_percent(
            top_code=top_code,
            major_id=major_id,
            major_riasec_map=major_riasec_map,
        )
        riasec_score = riasec_percent / 100

        # Subject Score
        major_combos = list({row["combination_code"] for row in rows})
        best_combo, best_total, subject_score = get_best_combo_for_major(
            major_combinations=major_combos,
            combo_results=combo_results,
        )

        if not best_combo:
            continue

        # Safety Score
        best_cutoff = 0.0
        for row in rows:
            if row["combination_code"] == best_combo:
                cutoff = float(row["cutoff_score"])
                if best_total >= cutoff and cutoff > best_cutoff:
                    best_cutoff = cutoff

        if best_cutoff == 0.0:
            continue

        safety_score = compute_safety_score(best_total, best_cutoff)

        # Geo Score = 0 trong Grid Search (không có địa lý)
        geo_score = 0.0

        # FinalScore với bộ trọng số đang thử
        final_score = (
            weights.alpha * riasec_score +
            weights.beta  * subject_score +
            weights.gamma * safety_score +
            weights.delta * geo_score
        )

        major_code = rows[0]["major_code"]
        scored.append((major_code, final_score))

    # Sắp xếp theo FinalScore giảm dần
    scored.sort(key=lambda x: x[1], reverse=True)
    return [code for code, _ in scored]


# ============================================================
# BƯỚC 3: Chạy Grid Search
# ============================================================

async def run_grid_search() -> dict:
    """
    Chạy toàn bộ Grid Search.

    Luồng:
    1. Load data DB + ground truth
    2. Sinh lưới trọng số
    3. Với mỗi bộ trọng số × K:
       a. Tính FinalScore cho mỗi hồ sơ
       b. Đánh giá bằng Evaluator
       c. Lưu kết quả
    4. Tìm bộ tốt nhất
    5. Lưu file JSON
    """

    print("=" * 60)
    print("GRID SEARCH — Tìm trọng số tối ưu")
    print("=" * 60)

    # Bước 1: Load data
    print("\nĐang load dữ liệu...")
    rows, major_riasec_map, combo_map = await asyncio.gather(
        load_eligible_majors(admission_year=ADMISSION_YEAR),
        build_major_riasec_map(),
        build_combination_subject_map(),
    )
    ground_truth = load_ground_truth()

    grouped = group_rows_by_major(rows)

    print(f"Ngành hợp lệ     : {len(grouped)}")
    print(f"Hồ sơ ground truth: {len(ground_truth)}")

    # Bước 2: Sinh lưới
    weight_configs = generate_weight_grid()
    total_runs = len(weight_configs) * len(K_GRID)
    print(f"Bộ trọng số      : {len(weight_configs)}")
    print(f"Giá trị K        : {K_GRID}")
    print(f"Tổng lần chạy    : {total_runs}")
    print()

    # Bước 3: Chạy từng tổ hợp
    all_results: list[GridSearchResult] = []
    run_count = 0

    for weights in weight_configs:
        # Pre-compute recommendations cho tất cả hồ sơ
        # với bộ trọng số này
        profile_recommendations = {}
        for profile in ground_truth:
            recommended = score_majors_for_profile(
                profile=profile,
                grouped=grouped,
                major_riasec_map=major_riasec_map,
                combo_map=combo_map,
                weights=weights,
            )
            profile_recommendations[profile["student_id"]] = recommended

        # Đánh giá với từng K
        for k in K_GRID:
            eval_results = []
            for profile in ground_truth:
                student_id = profile["student_id"]
                recommended = profile_recommendations[student_id]
                relevant = profile["relevant_majors"]

                result = evaluate_single(
                    student_id=student_id,
                    recommended_codes=recommended,
                    relevant_codes=relevant,
                    k=k,
                )
                eval_results.append(result)

            # Tổng hợp
            agg = evaluate_dataset(eval_results, k)

            all_results.append(GridSearchResult(
                alpha=weights.alpha,
                beta=weights.beta,
                gamma=weights.gamma,
                delta=weights.delta,
                k=k,
                mean_precision=agg.mean_precision,
                mean_ndcg=agg.mean_ndcg,
                mean_combined=agg.mean_combined,
                num_profiles=agg.num_profiles,
            ))

            run_count += 1
            if run_count % 50 == 0:
                print(f"  [{run_count:4d}/{total_runs}] "
                      f"α={weights.alpha} β={weights.beta} "
                      f"γ={weights.gamma} δ={weights.delta} "
                      f"K={k} → combined={agg.mean_combined:.4f}")

    # Bước 4: Tìm kết quả tốt nhất
    all_results.sort(key=lambda r: r.mean_combined, reverse=True)
    best = all_results[0]

    print()
    print("=" * 60)
    print("KẾT QUẢ TỐT NHẤT")
    print("=" * 60)
    print(f"α (RIASEC)  = {best.alpha}")
    print(f"β (Subject) = {best.beta}")
    print(f"γ (Safety)  = {best.gamma}")
    print(f"δ (Geo)     = {best.delta}")
    print(f"K           = {best.k}")
    print(f"Precision@K = {best.mean_precision:.4f}")
    print(f"NDCG@K      = {best.mean_ndcg:.4f}")
    print(f"Combined    = {best.mean_combined:.4f}")
    print()

    # Top 10 để phân tích
    print("Top 10 bộ trọng số tốt nhất:")
    for i, r in enumerate(all_results[:TOP_N_RESULTS]):
        print(
            f"  #{i+1:2d} "
            f"α={r.alpha} β={r.beta} γ={r.gamma} δ={r.delta} "
            f"K={r.k} → combined={r.mean_combined:.4f}"
        )

    # Bước 5: Lưu file
    output = {
        "best": asdict(best),
        "top_results": [asdict(r) for r in all_results[:TOP_N_RESULTS]],
        "all_results_count": len(all_results),
        "grid_config": {
            "weight_grid": WEIGHT_GRID,
            "k_grid": K_GRID,
            "admission_year": ADMISSION_YEAR,
            "num_profiles": len(ground_truth),
            "num_majors": len(grouped),
        }
    }

    GRID_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRID_RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Đã lưu kết quả: {GRID_RESULT_PATH}")
    return output


def load_best_weights() -> dict:
    """
    Load bộ trọng số tối ưu từ file JSON.
    Dùng trong Baseline 4 service.
    """
    if not GRID_RESULT_PATH.exists():
        raise FileNotFoundError(
            "Grid search chưa được chạy. "
            "Chạy run_grid_search() trước."
        )
    with open(GRID_RESULT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["best"]