# app/services/riasec_matcher.py
# Module độc lập tính Weighted Match Score giữa RIASEC học sinh và ngành
# Được tái sử dụng bởi Baseline 2, 3, 4

from app.db.data_loader import load_major_riasec


# ============================================================
# BƯỚC 1: Build position weights từ top_code
# ============================================================

# Trọng số theo vị trí trong mã Holland
# Vị trí #1 quan trọng nhất, #3 ít hơn
# Dùng tỷ lệ 3:2:1 — cơ sở: Holland nhấn mạnh 2 nhóm đầu
POSITION_WEIGHTS = {
    0: 1.00,   # Vị trí #1 — nhóm trội nhất
    1: 0.67,   # Vị trí #2
    2: 0.33,   # Vị trí #3
}

def build_student_riasec_vector(top_code: str) -> dict[str, float]:
    """
    Chuyển top_code thành vector có trọng số vị trí.

    Ví dụ:
        top_code = "RIA"
        → {"R": 1.00, "I": 0.67, "A": 0.33}

    Các nhóm không có trong top_code → không xuất hiện trong dict
    (tương đương weight = 0)
    """
    if not top_code or len(top_code) < 1:
        return {}

    vector = {}
    for idx, code in enumerate(top_code.upper()):
        if idx >= 3:
            break  # Chỉ lấy tối đa 3 nhóm
        if code in "RIASEC":
            vector[code] = POSITION_WEIGHTS.get(idx, 0.0)

    return vector


# ============================================================
# BƯỚC 2: Build RIASEC vector của ngành từ DB
# ============================================================

def build_major_riasec_vector(
    major_rows: list[dict],
    max_score: float = 3.0,
) -> dict[str, float]:
    """
    Chuyển các dòng RIASEC của 1 ngành thành vector normalize [0, 1].

    DB lưu score thang 1–3:
        sort_order=1 → nhóm RIASEC mạnh nhất của ngành
        sort_order=2 → mạnh thứ 2
        ...

    Normalize về [0, 1] bằng cách chia cho max_score (=3.0).

    Ví dụ ngành CNTT:
        [{"riasec_code": "I", "score": 3.0, "sort_order": 1},
         {"riasec_code": "R", "score": 2.8, "sort_order": 2},
         {"riasec_code": "C", "score": 2.0, "sort_order": 3}]
        → {"I": 1.0, "R": 0.93, "C": 0.67}
    """
    vector = {}
    for row in major_rows:
        code = row["riasec_code"].upper()
        raw_score = float(row["score"] or 0)
        vector[code] = round(raw_score / max_score, 4)

    return vector


# ============================================================
# BƯỚC 3: Tính Weighted Match Score
# ============================================================

def compute_weighted_match(
    student_vector: dict[str, float],
    major_vector: dict[str, float],
) -> float:
    """
    Tính Weighted Match Score giữa vector học sinh và vector ngành.

    Công thức:
        score = Σ (student_weight[g] × major_score[g]) / Σ student_weight[g]

    Ý nghĩa:
        - Mỗi nhóm học sinh có (R, I, A) được nhân với điểm ngành ở nhóm đó
        - Chia cho tổng trọng số để normalize về [0, 1]
        - Nhóm #1 của học sinh đóng góp nhiều nhất vào kết quả

    Ví dụ:
        student_vector = {"R": 1.0, "I": 0.67, "A": 0.33}
        major_vector   = {"I": 1.0, "R": 0.93, "C": 0.67}

        numerator   = 1.0×0.93 + 0.67×1.0 + 0.33×0.0 = 1.60
        denominator = 1.0 + 0.67 + 0.33 = 2.00
        score       = 1.60 / 2.00 = 0.80 → 80%
    """
    if not student_vector or not major_vector:
        return 0.0

    numerator = 0.0
    denominator = sum(student_vector.values())

    if denominator == 0:
        return 0.0

    for group, student_weight in student_vector.items():
        major_score = major_vector.get(group, 0.0)
        numerator += student_weight * major_score

    return round(numerator / denominator, 4)


# ============================================================
# BƯỚC 4: Build lookup map cho tất cả ngành (dùng chung)
# ============================================================

async def build_major_riasec_map() -> dict[str, dict[str, float]]:
    """
    Load toàn bộ RIASEC từ DB, build map:
        major_id → riasec_vector

    Gọi 1 lần ở đầu mỗi request — tránh query nhiều lần.

    Ví dụ kết quả:
        {
            "uuid-cntt": {"I": 1.0, "R": 0.93, "C": 0.67},
            "uuid-kinh-te": {"E": 1.0, "S": 0.87, "C": 0.73},
            ...
        }
    """
    rows = await load_major_riasec()

    # Gom nhóm các dòng theo major_id
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row["major_id"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row)

    # Build vector cho từng ngành
    major_riasec_map: dict[str, dict[str, float]] = {}
    for major_id, major_rows in grouped.items():
        major_riasec_map[major_id] = build_major_riasec_vector(major_rows)

    return major_riasec_map


# ============================================================
# ENTRY POINT: Tính match score cho 1 ngành
# ============================================================

def get_riasec_match_percent(
    top_code: str,
    major_id: str,
    major_riasec_map: dict[str, dict[str, float]],
) -> float:
    """
    Trả về % khớp RIASEC giữa học sinh và 1 ngành cụ thể.

    Trả về:
        float trong khoảng [0.0, 100.0]
        0.0 nếu ngành không có dữ liệu RIASEC
    """
    student_vector = build_student_riasec_vector(top_code)
    major_vector = major_riasec_map.get(major_id, {})

    if not major_vector:
        return 0.0

    score = compute_weighted_match(student_vector, major_vector)
    return round(score * 100, 2)  # Chuyển về %