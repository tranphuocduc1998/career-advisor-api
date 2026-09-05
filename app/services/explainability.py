# app/services/explainability.py
# Tạo giải thích ngôn ngữ tự nhiên cho kết quả gợi ý
# Baseline 4: Điểm từng chiều + Key Factor

from dataclasses import dataclass
from app.models.schemas import DimensionBreakdown


# ============================================================
# KIỂU DỮ LIỆU
# ============================================================

@dataclass
class ExplanationResult:
    """Kết quả giải thích đầy đủ cho 1 ngành"""
    dimensions: list[DimensionBreakdown]
    key_factor: str          # Chiều ảnh hưởng nhiều nhất
    key_factor_label: str    # Tên tiếng Việt của key factor
    primary_reason: str      # Câu giải thích chính
    secondary_reasons: list[str]  # Các lý do phụ


# ============================================================
# CONFIG NHÃN VÀ NGƯỠNG
# ============================================================

DIMENSION_META = {
    "riasec": {
        "label":  "Định hướng nghề nghiệp",
        "high":   "Ngành này khớp sâu với kiểu tư duy và sở thích nghề nghiệp của bạn",
        "medium": "Ngành này tương đối phù hợp với định hướng nghề nghiệp của bạn",
        "low":    "Ngành này chỉ phù hợp một phần với định hướng nghề nghiệp của bạn",
    },
    "subject": {
        "label":  "Năng lực học tập",
        "high":   "Điểm tổ hợp môn của bạn rất tốt cho ngành này",
        "medium": "Điểm tổ hợp môn của bạn đáp ứng yêu cầu ngành",
        "low":    "Điểm tổ hợp môn của bạn ở mức vừa đủ cho ngành này",
    },
    "safety": {
        "label":  "Biên an toàn",
        "high":   "Điểm của bạn vượt điểm chuẩn với biên an toàn cao — tự tin đăng ký",
        "medium": "Điểm của bạn vượt điểm chuẩn ở mức vừa đủ",
        "low":    "Điểm của bạn vừa đủ điểm chuẩn — cân nhắc kỹ trước khi đăng ký",
    },
    "geo": {
        "label":  "Ưu tiên địa lý",
        "high":   "Có trường đào tạo ngành này tại đúng khu vực bạn mong muốn",
        "medium": "Có trường đào tạo ngành này tại tỉnh/thành bạn mong muốn",
        "low":    "Không có ràng buộc địa lý hoặc không khớp khu vực ưu tiên",
    },
}

# Ngưỡng phân loại mức độ
HIGH_THRESHOLD   = 0.65
MEDIUM_THRESHOLD = 0.35


# ============================================================
# BƯỚC 1: Phân loại mức độ từng chiều
# ============================================================

def classify_level(score: float) -> str:
    """Phân loại score thành high / medium / low"""
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ============================================================
# BƯỚC 2: Build DimensionBreakdown cho từng chiều
# ============================================================

def build_dimensions(
    riasec_score: float,
    subject_score: float,
    safety_score: float,
    geo_score: float,
    weights: dict[str, float],
) -> list[DimensionBreakdown]:
    """
    Build danh sách DimensionBreakdown cho 4 chiều.

    Tham số:
        riasec_score  : [0, 1]
        subject_score : [0, 1]
        safety_score  : [0, 1]
        geo_score     : [0, 1]
        weights       : {"alpha": 0.7, "beta": 0.1, "gamma": 0.1, "delta": 0.1}
    """
    raw = {
        "riasec":  (riasec_score,  weights["alpha"]),
        "subject": (subject_score, weights["beta"]),
        "safety":  (safety_score,  weights["gamma"]),
        "geo":     (geo_score,     weights["delta"]),
    }

    dimensions = []
    for key, (score, weight) in raw.items():
        meta = DIMENSION_META[key]
        level = classify_level(score)
        contribution = round(score * weight, 4)

        dimensions.append(DimensionBreakdown(
            label=meta["label"],
            score=round(score, 4),
            weight=weight,
            contribution=contribution,
            explanation=meta[level],
        ))

    return dimensions


# ============================================================
# BƯỚC 3: Xác định Key Factor
# ============================================================

def find_key_factor(
    dimensions: list[DimensionBreakdown],
) -> tuple[str, str]:
    """
    Tìm chiều đóng góp nhiều nhất vào FinalScore.

    Trả về:
        (key_factor_code, key_factor_label)
        VD: ("riasec", "Định hướng nghề nghiệp")
    """
    dim_keys = ["riasec", "subject", "safety", "geo"]

    # Tìm dimension có contribution cao nhất
    top_dim = max(dimensions, key=lambda d: d.contribution)
    top_idx = [d.label for d in dimensions].index(top_dim.label)

    key = dim_keys[top_idx]
    label = DIMENSION_META[key]["label"]

    return key, label


# ============================================================
# BƯỚC 4: Build câu giải thích
# ============================================================

def build_primary_reason(
    top_code: str,
    major_name: str,
    key_factor: str,
    riasec_percent: float,
    best_combo: str,
    student_total: float,
    cutoff: float,
    final_score: float,
) -> str:
    """
    Tạo câu giải thích chính dựa trên key factor.

    Mỗi key factor có câu giải thích riêng —
    tập trung vào yếu tố quan trọng nhất.
    """
    safety_margin = round(student_total - cutoff, 1)

    if final_score >= 0.75:
        overall = "rất phù hợp"
    elif final_score >= 0.55:
        overall = "phù hợp"
    else:
        overall = "có thể cân nhắc"

    reason_map = {
        "riasec": (
            f"Ngành {major_name} {overall} với bạn — "
            f"mã Holland {top_code} khớp {riasec_percent:.1f}% "
            f"với đặc trưng nghề nghiệp của ngành này."
        ),
        "subject": (
            f"Ngành {major_name} {overall} với bạn — "
            f"điểm tổ hợp {best_combo} ({student_total:.1f}đ) "
            f"của bạn rất mạnh so với yêu cầu ngành."
        ),
        "safety": (
            f"Ngành {major_name} {overall} với bạn — "
            f"điểm tổ hợp {best_combo} ({student_total:.1f}đ) "
            f"vượt điểm chuẩn {cutoff:.1f}đ, dư {safety_margin}đ an toàn."
        ),
        "geo": (
            f"Ngành {major_name} {overall} với bạn — "
            f"có trường đào tạo tại khu vực bạn mong muốn "
            f"với tổ hợp {best_combo} ({student_total:.1f}đ)."
        ),
    }

    return reason_map.get(key_factor, reason_map["riasec"])


def build_secondary_reasons(
    dimensions: list[DimensionBreakdown],
    key_factor_label: str,
) -> list[str]:
    """
    Tạo danh sách lý do phụ từ các chiều còn lại.
    Chỉ lấy chiều có contribution >= 0.05.
    Bỏ qua chiều đã dùng làm key factor.
    """
    secondary = []

    for dim in sorted(dimensions, key=lambda d: d.contribution, reverse=True):
        if dim.label == key_factor_label:
            continue
        if dim.contribution < 0.05:
            continue
        secondary.append(dim.explanation)

    return secondary[:2]  # Tối đa 2 lý do phụ


# ============================================================
# ENTRY POINT: Tạo giải thích đầy đủ cho 1 ngành
# ============================================================

def explain_recommendation(
    top_code: str,
    major_name: str,
    riasec_score: float,
    subject_score: float,
    safety_score: float,
    geo_score: float,
    best_combo: str,
    student_total: float,
    cutoff: float,
    final_score: float,
    weights: dict[str, float],
) -> ExplanationResult:
    """
    Tạo giải thích đầy đủ cho 1 ngành được gợi ý.

    Trả về ExplanationResult gồm:
        - dimensions     : điểm + giải thích 4 chiều
        - key_factor     : chiều ảnh hưởng nhiều nhất
        - primary_reason : câu giải thích chính
        - secondary_reasons: lý do phụ
    """
    # Build dimensions
    dimensions = build_dimensions(
        riasec_score=riasec_score,
        subject_score=subject_score,
        safety_score=safety_score,
        geo_score=geo_score,
        weights=weights,
    )

    # Tìm key factor
    key_factor, key_factor_label = find_key_factor(dimensions)

    # Build giải thích
    riasec_percent = round(riasec_score * 100, 1)
    primary = build_primary_reason(
        top_code=top_code,
        major_name=major_name,
        key_factor=key_factor,
        riasec_percent=riasec_percent,
        best_combo=best_combo,
        student_total=student_total,
        cutoff=cutoff,
        final_score=final_score,
    )
    secondary = build_secondary_reasons(dimensions, key_factor_label)

    return ExplanationResult(
        dimensions=dimensions,
        key_factor=key_factor,
        key_factor_label=key_factor_label,
        primary_reason=primary,
        secondary_reasons=secondary,
    )
    