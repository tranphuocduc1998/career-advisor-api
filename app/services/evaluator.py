# app/services/evaluator.py
# Đánh giá chất lượng gợi ý bằng Precision@K và NDCG@K
# Thiết kế K động — không hard-code

import math
from dataclasses import dataclass


# ============================================================
# KIỂU DỮ LIỆU KẾT QUẢ ĐÁNH GIÁ
# ============================================================

@dataclass
class EvalResult:
    """Kết quả đánh giá cho 1 hồ sơ học sinh"""
    student_id: str
    k: int
    precision_at_k: float       # [0, 1]
    ndcg_at_k: float            # [0, 1]
    combined_score: float       # Trung bình có trọng số
    num_relevant: int           # Số ngành relevant trong ground truth
    num_retrieved: int          # Số ngành được gợi ý
    num_hits: int               # Số ngành relevant trong top K


@dataclass
class AggregateEvalResult:
    """Kết quả đánh giá tổng hợp trên toàn bộ dataset"""
    k: int
    mean_precision: float
    mean_ndcg: float
    mean_combined: float
    num_profiles: int           # Số hồ sơ được đánh giá
    num_skipped: int            # Số hồ sơ bị bỏ qua (không có relevant)


# ============================================================
# PRECISION@K
# ============================================================

def precision_at_k(
    recommended: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    Tính Precision@K — tỷ lệ ngành relevant trong top K gợi ý.

    Công thức:
        P@K = |relevant ∩ top_K_recommended| / K

    Ví dụ:
        recommended = ["CNTT", "KT", "XD", "YK", "LS"]
        relevant    = ["CNTT", "YK", "SP"]
        K = 5

        hits = {"CNTT", "YK"} → 2 ngành
        P@5 = 2 / 5 = 0.40

    Lưu ý:
        - Chia cho K (không phải số hits) — đây là định nghĩa chuẩn
        - Nếu recommended < K → chia cho len(recommended)
    """
    if not recommended or not relevant:
        return 0.0

    top_k = recommended[:k]
    relevant_set = set(relevant)
    hits = sum(1 for item in top_k if item in relevant_set)

    return hits / min(k, len(top_k))


# ============================================================
# NDCG@K
# ============================================================

def dcg_at_k(
    recommended: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    Tính DCG@K (Discounted Cumulative Gain).

    Công thức:
        DCG@K = Σ rel_i / log2(i + 2)   với i = 0..K-1

    rel_i = 1 nếu item thứ i là relevant, 0 nếu không.

    Ý nghĩa: Ngành relevant ở vị trí cao → đóng góp nhiều hơn.
    """
    relevant_set = set(relevant)
    dcg = 0.0

    for i, item in enumerate(recommended[:k]):
        if item in relevant_set:
            # i+2 vì log2(1) = 0, dùng i+2 để tránh chia 0
            dcg += 1.0 / math.log2(i + 2)

    return dcg


def ideal_dcg_at_k(
    relevant: list[str],
    k: int,
) -> float:
    """
    Tính Ideal DCG@K — DCG tốt nhất có thể đạt được.
    Giả định tất cả relevant được xếp ở đầu danh sách.

    IDCG@K = Σ 1/log2(i+2) với i = 0..min(K, |relevant|)-1
    """
    ideal_hits = min(k, len(relevant))
    return sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))


def ndcg_at_k(
    recommended: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    Tính NDCG@K (Normalized Discounted Cumulative Gain).

    Công thức:
        NDCG@K = DCG@K / IDCG@K

    Ý nghĩa:
        1.0 = hoàn hảo (tất cả relevant ở đầu danh sách)
        0.0 = không có ngành relevant nào trong top K

    Ví dụ:
        recommended = ["CNTT", "KT", "XD", "YK", "LS"]
        relevant    = ["CNTT", "YK"]
        K = 5

        DCG  = 1/log2(2) + 1/log2(4) = 1.0 + 0.5 = 1.5
        IDCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.63 = 1.63
        NDCG = 1.5 / 1.63 = 0.92
    """
    if not relevant:
        return 0.0

    dcg = dcg_at_k(recommended, relevant, k)
    idcg = ideal_dcg_at_k(relevant, k)

    if idcg == 0:
        return 0.0

    return dcg / idcg


# ============================================================
# COMBINED SCORE
# ============================================================

def combined_score(
    p_at_k: float,
    n_at_k: float,
    alpha: float = 0.5,
) -> float:
    """
    Kết hợp Precision@K và NDCG@K thành 1 điểm duy nhất.

    Công thức:
        Combined = alpha * P@K + (1 - alpha) * NDCG@K

    Mặc định alpha=0.5 → trọng số bằng nhau.
    Grid Search có thể điều chỉnh alpha nếu muốn ưu tiên 1 metric.
    """
    return alpha * p_at_k + (1 - alpha) * n_at_k


# ============================================================
# EVALUATE 1 HỒ SƠ
# ============================================================

def evaluate_single(
    student_id: str,
    recommended_codes: list[str],
    relevant_codes: list[str],
    k: int,
    alpha: float = 0.5,
) -> EvalResult:
    """
    Đánh giá kết quả gợi ý cho 1 hồ sơ học sinh.

    Tham số:
        student_id       : ID học sinh
        recommended_codes: list major_code được gợi ý (đã sắp xếp theo score)
        relevant_codes   : list major_code trong ground truth
        k                : ngưỡng đánh giá
        alpha            : trọng số P@K trong combined score
    """
    p = precision_at_k(recommended_codes, relevant_codes, k)
    n = ndcg_at_k(recommended_codes, relevant_codes, k)
    c = combined_score(p, n, alpha)

    relevant_set = set(relevant_codes)
    hits = sum(1 for code in recommended_codes[:k] if code in relevant_set)

    return EvalResult(
        student_id=student_id,
        k=k,
        precision_at_k=round(p, 4),
        ndcg_at_k=round(n, 4),
        combined_score=round(c, 4),
        num_relevant=len(relevant_codes),
        num_retrieved=len(recommended_codes),
        num_hits=hits,
    )


# ============================================================
# EVALUATE TOÀN BỘ DATASET
# ============================================================

def evaluate_dataset(
    results: list[EvalResult],
    k: int,
) -> AggregateEvalResult:
    """
    Tổng hợp kết quả đánh giá trên toàn bộ dataset.
    Bỏ qua hồ sơ không có relevant majors.
    """
    valid = [r for r in results if r.num_relevant > 0]
    skipped = len(results) - len(valid)

    if not valid:
        return AggregateEvalResult(
            k=k,
            mean_precision=0.0,
            mean_ndcg=0.0,
            mean_combined=0.0,
            num_profiles=0,
            num_skipped=skipped,
        )

    mean_p = sum(r.precision_at_k for r in valid) / len(valid)
    mean_n = sum(r.ndcg_at_k for r in valid) / len(valid)
    mean_c = sum(r.combined_score for r in valid) / len(valid)

    return AggregateEvalResult(
        k=k,
        mean_precision=round(mean_p, 4),
        mean_ndcg=round(mean_n, 4),
        mean_combined=round(mean_c, 4),
        num_profiles=len(valid),
        num_skipped=skipped,
    )


# ============================================================
# TÌM K TỐI ƯU
# ============================================================

def find_best_k(
    all_results_by_k: dict[int, AggregateEvalResult],
) -> int:
    """
    Trong các K đã thử, tìm K cho combined score cao nhất.

    Tham số:
        all_results_by_k: {k: AggregateEvalResult}

    Trả về:
        K tối ưu
    """
    best_k = max(
        all_results_by_k.keys(),
        key=lambda k: all_results_by_k[k].mean_combined,
    )
    return best_k