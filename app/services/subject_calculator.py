# app/services/subject_calculator.py
# Tính điểm học sinh theo từng tổ hợp môn
# Key: subject_code từ DB (MATH, PHYSICS, CHEMISTRY,...)
# Dùng chung cho Baseline 3 và 4

from app.db.data_loader import load_combination_subjects


# ============================================================
# CONSTANTS
# ============================================================

MAX_COMBO_SCORE = 30.0  # 3 môn × 10 điểm tối đa

# Map subject_code → name_vi để hiển thị UI
SUBJECT_CODE_TO_NAME: dict[str, str] = {
    "MATH":                 "Toán",
    "LITERATURE":           "Ngữ văn",
    "ENGLISH":              "Tiếng Anh",
    "PHYSICS":              "Vật lí",
    "CHEMISTRY":            "Hóa học",
    "BIOLOGY":              "Sinh học",
    "HISTORY":              "Lịch sử",
    "GEOGRAPHY":            "Địa lí",
    "ECONOMICS_LAW":        "Giáo dục kinh tế và pháp luật",
    "INFORMATICS":          "Tin học",
    "FINE_ARTS":            "Mỹ thuật",
    "MUSIC":                "Âm nhạc",
    "AGRICULTURAL_TECHNOLOGY":  "Công nghệ nông nghiệp",
    "INDUSTRIAL_TECHNOLOGY":    "Công nghệ công nghiệp",
}


# ============================================================
# KIỂU DỮ LIỆU NỘI BỘ
# ============================================================

class ComboResult:
    """Kết quả tính điểm của 1 tổ hợp môn"""
    def __init__(
        self,
        combination_code: str,
        total_score: float,
        subject_scores: dict[str, float],  # key: subject_code
        is_valid: bool,
        missing_subjects: list[str],        # subject_code còn thiếu
    ):
        self.combination_code = combination_code
        self.total_score = total_score
        self.subject_scores = subject_scores
        self.is_valid = is_valid
        self.missing_subjects = missing_subjects

    @property
    def missing_subject_names(self) -> list[str]:
        """Trả về tên tiếng Việt của các môn còn thiếu — dùng cho UI"""
        return [
            SUBJECT_CODE_TO_NAME.get(code, code)
            for code in self.missing_subjects
        ]

    def __repr__(self):
        return (
            f"ComboResult({self.combination_code}: "
            f"total={self.total_score} | valid={self.is_valid} "
            f"| missing={self.missing_subjects})"
        )


# ============================================================
# BƯỚC 1: Build lookup map tổ hợp → danh sách subject_code
# ============================================================

async def build_combination_subject_map() -> dict[str, list[str]]:
    """
    Load DB và build map:
        combination_code → [subject_code, ...]

    Ví dụ:
        {
            "A00": ["MATH", "PHYSICS", "CHEMISTRY"],
            "A01": ["MATH", "PHYSICS", "ENGLISH"],
            "D01": ["MATH", "LITERATURE", "ENGLISH"],
        }
    """
    rows = await load_combination_subjects()

    combo_map: dict[str, list[str]] = {}
    for row in rows:
        code = row["combination_code"]
        subject_code = row["subject_code"]

        if code not in combo_map:
            combo_map[code] = []
        combo_map[code].append(subject_code)

    return combo_map


# ============================================================
# BƯỚC 2: Tính điểm học sinh theo từng tổ hợp
# ============================================================

def calculate_combo_scores(
    student_scores: dict[str, float],
    combo_map: dict[str, list[str]],
) -> dict[str, ComboResult]:
    """
    Tính điểm học sinh cho tất cả tổ hợp có trong DB.

    Tham số:
        student_scores: {"MATH": 8.5, "PHYSICS": 7.0, "ENGLISH": 9.0}
        combo_map     : {"A00": ["MATH", "PHYSICS", "CHEMISTRY"], ...}

    Ví dụ:
        A00 cần: MATH(8.5) + PHYSICS(7.0) + CHEMISTRY(?) → thiếu → invalid
        A01 cần: MATH(8.5) + PHYSICS(7.0) + ENGLISH(9.0) → đủ → 24.5
        D01 cần: MATH(8.5) + LITERATURE(?) + ENGLISH(9.0) → thiếu → invalid
    """
    results: dict[str, ComboResult] = {}

    for combo_code, subject_codes in combo_map.items():
        subject_scores_for_combo: dict[str, float] = {}
        missing: list[str] = []

        for subject_code in subject_codes:
            if subject_code in student_scores:
                subject_scores_for_combo[subject_code] = student_scores[subject_code]
            else:
                missing.append(subject_code)

        is_valid = len(missing) == 0
        total = sum(subject_scores_for_combo.values()) if is_valid else 0.0

        results[combo_code] = ComboResult(
            combination_code=combo_code,
            total_score=round(total, 2),
            subject_scores=subject_scores_for_combo,
            is_valid=is_valid,
            missing_subjects=missing,
        )

    return results


# ============================================================
# BƯỚC 3: Tính SubjectScore normalize [0, 1]
# ============================================================

def compute_subject_score(
    combo_results: dict[str, ComboResult],
    combination_code: str,
) -> float:
    """
    Normalize điểm tổ hợp về [0, 1].

    Công thức:
        SubjectScore = total_score / MAX_COMBO_SCORE (30.0)

    Ví dụ:
        total = 24.5 → SubjectScore = 24.5 / 30 = 0.8167
    """
    result = combo_results.get(combination_code)

    if not result or not result.is_valid:
        return 0.0

    return round(result.total_score / MAX_COMBO_SCORE, 4)


# ============================================================
# BƯỚC 4: Tìm tổ hợp tốt nhất cho 1 ngành
# ============================================================

def get_best_combo_for_major(
    major_combinations: list[str],
    combo_results: dict[str, ComboResult],
) -> tuple[str, float, float]:
    """
    Trong số các tổ hợp ngành chấp nhận,
    tìm tổ hợp học sinh có điểm cao nhất.

    Trả về:
        (best_combo_code, total_score, subject_score_normalized)
        ("", 0.0, 0.0) nếu không có tổ hợp hợp lệ
    """
    best_combo = ""
    best_total = 0.0
    best_subject_score = 0.0

    for combo_code in major_combinations:
        result = combo_results.get(combo_code)
        if not result or not result.is_valid:
            continue

        if result.total_score > best_total:
            best_total = result.total_score
            best_combo = combo_code
            best_subject_score = compute_subject_score(
                combo_results, combo_code
            )

    return best_combo, best_total, best_subject_score