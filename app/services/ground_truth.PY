# app/services/ground_truth.py
# Sinh Ground Truth Dataset tự động cho Grid Search
# Hướng 3: Kết hợp quy tắc Holland + điểm số

import json
import random
from pathlib import Path
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

# ============================================================
# CONSTANTS
# ============================================================

# Ngưỡng RIASEC match để coi là "phù hợp"
RIASEC_THRESHOLD = 65.0

# Năm tuyển sinh dùng để sinh ground truth
ADMISSION_YEAR = 2026

# Số hồ sơ học sinh mẫu cần sinh
NUM_PROFILES = 50

# File lưu ground truth
GROUND_TRUTH_PATH = Path("app/data/ground_truth.json")

# Tất cả mã Holland hợp lệ
RIASEC_CODES = ["R", "I", "A", "S", "E", "C"]

# Các bộ top_code đa dạng để sinh hồ sơ mẫu
SAMPLE_TOP_CODES = [
    "RIA", "RIS", "RIC", "RIE",
    "IRA", "IAS", "IAE", "IAC",
    "ARI", "AIE", "AIS", "AIC",
    "SIA", "SIE", "SAE", "SAI",
    "EIS", "ESA", "EAS", "EAI",
    "CIS", "CIA", "CRS", "CRI",
    "RAS", "ISC", "AES", "SEC",
]

# Các bộ điểm môn học sinh mẫu — đa dạng mức điểm
SAMPLE_SCORE_PROFILES = [
    # Giỏi toàn diện
    {"MATH": 9.0, "PHYSICS": 8.5, "CHEMISTRY": 8.0,
     "ENGLISH": 9.0, "LITERATURE": 8.0, "BIOLOGY": 8.5},
    # Mạnh khối A
    {"MATH": 9.5, "PHYSICS": 9.0, "CHEMISTRY": 8.5,
     "ENGLISH": 7.0, "LITERATURE": 6.5},
    # Mạnh khối D
    {"MATH": 8.0, "LITERATURE": 8.5, "ENGLISH": 9.5,
     "HISTORY": 8.0, "GEOGRAPHY": 7.5},
    # Mạnh khối B
    {"MATH": 8.0, "BIOLOGY": 9.0, "CHEMISTRY": 8.5,
     "LITERATURE": 7.0, "ENGLISH": 7.5},
    # Trung bình khá
    {"MATH": 7.0, "PHYSICS": 7.0, "CHEMISTRY": 6.5,
     "ENGLISH": 7.5, "LITERATURE": 7.0},
    # Điểm vừa đủ
    {"MATH": 6.0, "PHYSICS": 6.0, "CHEMISTRY": 5.5,
     "ENGLISH": 6.5, "LITERATURE": 6.0, "BIOLOGY": 6.0},
    # Mạnh Lịch sử - Địa lý
    {"LITERATURE": 9.0, "HISTORY": 9.0, "GEOGRAPHY": 8.5,
     "ENGLISH": 8.0, "MATH": 7.0},
    # Mạnh Tin học
    {"MATH": 9.0, "INFORMATICS": 9.5, "PHYSICS": 8.0,
     "ENGLISH": 8.5, "CHEMISTRY": 7.0},
]


# ============================================================
# BƯỚC 1: Sinh hồ sơ học sinh mẫu
# ============================================================

def generate_student_profiles(n: int = NUM_PROFILES) -> list[dict]:
    """
    Sinh n hồ sơ học sinh mẫu đa dạng.

    Mỗi hồ sơ gồm:
        - student_id : định danh
        - top_code   : mã Holland (VD: "RIA")
        - scores     : điểm các môn học

    Đảm bảo đa dạng:
        - Mỗi top_code xuất hiện ít nhất 1 lần
        - Điểm số đa dạng mức giỏi / khá / trung bình
    """
    profiles = []

    # Đảm bảo đủ các top_code mẫu
    base_codes = SAMPLE_TOP_CODES[:n]
    if n > len(SAMPLE_TOP_CODES):
        # Random thêm nếu cần nhiều hơn
        extras = [
            "".join(random.sample(RIASEC_CODES, 3))
            for _ in range(n - len(SAMPLE_TOP_CODES))
        ]
        base_codes = base_codes + extras

    for i in range(n):
        top_code = base_codes[i % len(base_codes)]

        # Xoay vòng các bộ điểm mẫu
        score_profile = SAMPLE_SCORE_PROFILES[i % len(SAMPLE_SCORE_PROFILES)]

        # Thêm nhiễu nhỏ để các hồ sơ không giống hệt nhau
        noisy_scores = {
            subject: round(
                max(0.0, min(10.0, score + random.uniform(-0.5, 0.5))),
                1
            )
            for subject, score in score_profile.items()
        }

        profiles.append({
            "student_id": f"student_{i+1:03d}",
            "top_code": top_code,
            "scores": noisy_scores,
        })

    return profiles


# ============================================================
# BƯỚC 2: Xác định ngành phù hợp cho từng hồ sơ
# ============================================================

async def find_relevant_majors(
    profile: dict,
    major_riasec_map: dict,
    combo_map: dict,
    all_rows: list[dict],
) -> list[str]:
    """
    Với 1 hồ sơ học sinh, tìm danh sách major_code phù hợp.

    Tiêu chí (Hướng 3):
        1. RIASEC match >= RIASEC_THRESHOLD (65%)
        2. Học sinh đủ điểm ít nhất 1 tổ hợp của ngành
        3. Tổng điểm tổ hợp tốt nhất >= điểm chuẩn ít nhất 1 trường

    Trả về list[major_code] — danh sách ngành "phù hợp"
    """
    top_code = profile["top_code"]
    student_scores = profile["scores"]

    # Tính điểm tổ hợp của học sinh
    combo_results = calculate_combo_scores(student_scores, combo_map)

    # Gom nhóm rows theo major
    from app.services.content_based import group_rows_by_major
    grouped = group_rows_by_major(all_rows)

    relevant = []

    for major_id, rows in grouped.items():
        # Tiêu chí 1: RIASEC match
        match_percent = get_riasec_match_percent(
            top_code=top_code,
            major_id=major_id,
            major_riasec_map=major_riasec_map,
        )
        if match_percent < RIASEC_THRESHOLD:
            continue

        # Tiêu chí 2 & 3: Đủ điểm tổ hợp + vượt điểm chuẩn
        major_combos = list({row["combination_code"] for row in rows})
        best_combo, best_total, _ = get_best_combo_for_major(
            major_combinations=major_combos,
            combo_results=combo_results,
        )

        if not best_combo:
            continue

        # Kiểm tra vượt điểm chuẩn ít nhất 1 trường
        passed_cutoff = any(
            row["combination_code"] == best_combo
            and best_total >= float(row["cutoff_score"])
            for row in rows
        )

        if passed_cutoff:
            relevant.append(rows[0]["major_code"])

    return relevant


# ============================================================
# BƯỚC 3: Sinh và lưu toàn bộ Ground Truth
# ============================================================

async def generate_and_save_ground_truth():
    """
    Sinh toàn bộ Ground Truth Dataset và lưu vào JSON.

    Output format:
    [
        {
            "student_id": "student_001",
            "top_code": "RIA",
            "scores": {"MATH": 8.5, ...},
            "relevant_majors": ["7480201", "7480202", ...]
        },
        ...
    ]
    """
    print("Đang load dữ liệu từ DB...")

    import asyncio
    all_rows, major_riasec_map, combo_map = await asyncio.gather(
        load_eligible_majors(admission_year=ADMISSION_YEAR),
        build_major_riasec_map(),
        build_combination_subject_map(),
    )

    print(f"Load xong: {len(all_rows)} dòng | "
          f"{len(major_riasec_map)} ngành có RIASEC")

    # Sinh hồ sơ mẫu
    profiles = generate_student_profiles(NUM_PROFILES)
    print(f"Đã sinh {len(profiles)} hồ sơ học sinh mẫu")

    # Tìm ngành phù hợp cho từng hồ sơ
    dataset = []
    for i, profile in enumerate(profiles):
        relevant = await find_relevant_majors(
            profile=profile,
            major_riasec_map=major_riasec_map,
            combo_map=combo_map,
            all_rows=all_rows,
        )

        dataset.append({
            "student_id": profile["student_id"],
            "top_code": profile["top_code"],
            "scores": profile["scores"],
            "relevant_majors": relevant,
        })

        print(f"[{i+1:3d}/{NUM_PROFILES}] {profile['student_id']} "
              f"({profile['top_code']}) → {len(relevant)} ngành phù hợp")

    # Lưu file
    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Đã lưu ground truth: {GROUND_TRUTH_PATH}")
    print(f"   Tổng hồ sơ          : {len(dataset)}")
    print(f"   Hồ sơ có ngành PH   : {sum(1 for d in dataset if d['relevant_majors'])}")
    avg = sum(len(d['relevant_majors']) for d in dataset) / len(dataset)
    print(f"   TB ngành/hồ sơ      : {avg:.1f}")

    return dataset


def load_ground_truth() -> list[dict]:
    """Load ground truth từ file JSON đã sinh"""
    if not GROUND_TRUTH_PATH.exists():
        raise FileNotFoundError(
            f"Ground truth chưa được sinh. "
            f"Chạy generate_and_save_ground_truth() trước."
        )
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)