# app/services/random_recommender.py

import random
from uuid import UUID
from typing import Optional
from app.db.data_loader import load_eligible_majors
from app.models.schemas import (
    MajorRecommendation,
    BestAdmissionPath,
    RecommendationResponse,
    RIASECScore,
)


def _group_rows_by_major(rows: list[dict]) -> dict[str, list[dict]]:
    """
    Gom nhóm các dòng DB theo major_id.

    Vì sao cần gom nhóm:
    - 1 ngành có thể có nhiều tổ hợp (A00, A01, D01...)
    - 1 ngành có thể được đào tạo ở nhiều trường
    - Query trả về 1 dòng cho mỗi cặp (ngành, trường, tổ hợp)
    - Cần gom lại thành 1 ngành với nhiều đường xét tuyển
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row["major_id"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row)
    return grouped


def _build_admission_paths(rows: list[dict]) -> list[BestAdmissionPath]:
    """
    Từ các dòng cùng 1 ngành, build danh sách đường xét tuyển.
    Mỗi dòng = 1 cặp (trường, tổ hợp, điểm chuẩn).
    Sắp xếp theo cutoff_score giảm dần — trường điểm cao lên trước.
    """
    paths = []
    for row in rows:
        paths.append(BestAdmissionPath(
            institution_id=row["institution_id"],
            institution_name=str(row["institution_name"]),  # Tạm dùng ID
            # vì educational_institution chưa có cột name —
            # sẽ cập nhật khi bạn cung cấp tên cột tên trường
            campus_id=row["campus_id"],
            combination_code=row["combination_code"],
            student_score=0.0,   # Baseline 1 không tính điểm học sinh
            cutoff_score=float(row["cutoff_score"]),
            safety_margin=0.0,   # Baseline 1 không tính safety margin
        ))

    # Sắp xếp theo điểm chuẩn giảm dần
    paths.sort(key=lambda p: p.cutoff_score, reverse=True)
    return paths


def _build_major_recommendation(
    major_id: str,
    rows: list[dict],
) -> MajorRecommendation:
    """
    Từ danh sách dòng cùng 1 ngành,
    build 1 MajorRecommendation hoàn chỉnh.
    """
    first = rows[0]  # Lấy dòng đầu cho thông tin chung của ngành
    admission_paths = _build_admission_paths(rows)

    return MajorRecommendation(
        major_id=first["major_id"],
        major_code=first["major_code"],
        major_name_vi=first["major_name_vi"],
        major_name_en=first["major_name_en"],
        field_name_vi=first["field_name_vi"],
        group_name_vi=first["group_name_vi"],
        final_score=0.0,            # Baseline 1: không có điểm xếp hạng
        riasec_match_percent=0.0,   # Baseline 1: không tính RIASEC
        best_paths=admission_paths,
        dimensions=None,            # Baseline 1: không có explainability
        primary_reason="Gợi ý ngẫu nhiên từ danh sách ngành đang tuyển sinh",
    )


async def run_random_recommender(
    admission_year: int,
    top_n: int,
    province_id: Optional[UUID] = None,
    district_id: Optional[UUID] = None,
    riasec_scores: Optional[RIASECScore] = None,
) -> RecommendationResponse:
    """
    CORE: Chạy Random Recommender.

    Luồng xử lý:
    1. Load toàn bộ ngành hợp lệ từ DB (đã lọc địa lý + năm)
    2. Gom nhóm theo ngành
    3. Random chọn top_n ngành
    4. Build response
    """

    # Bước 1: Load dữ liệu từ DB
    rows = await load_eligible_majors(
        admission_year=admission_year,
        province_id=province_id,
        district_id=district_id,
    )

    if not rows:
        return RecommendationResponse(
            baseline="random",
            riasec_code=riasec_scores.top_code if riasec_scores else "N/A",
            total_candidates=0,
            results=[],
        )

    # Bước 2: Gom nhóm theo ngành
    grouped = _group_rows_by_major(rows)
    total_candidates = len(grouped)

    # Bước 3: Random chọn top_n ngành
    all_major_ids = list(grouped.keys())
    selected_ids = random.sample(
        all_major_ids,
        k=min(top_n, total_candidates)  # Không random quá số ngành có
    )

    # Bước 4: Build kết quả
    results = []
    for major_id in selected_ids:
        recommendation = _build_major_recommendation(
            major_id=major_id,
            rows=grouped[major_id],
        )
        results.append(recommendation)

    return RecommendationResponse(
        baseline="random",
        riasec_code=riasec_scores.top_code if riasec_scores else "N/A",
        total_candidates=total_candidates,
        results=results,
    )