from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


# ============================================================
# INTERNAL SCHEMAS — Dùng nội bộ giữa các service
# ============================================================

class SubjectScore(BaseModel):
    """Điểm một môn học của học sinh"""
    subject_code: str        # VD: "TOAN", "LY", "HOA"
    subject_name: str        # VD: "Toán", "Vật lý"
    score: float = Field(ge=0.0, le=10.0)  # Thang điểm 10


class CombinationScore(BaseModel):
    """Tổ hợp môn và tổng điểm tính được"""
    combination_code: str    # VD: "A00", "A01"
    total_score: float       # Tổng 3 môn
    subjects: list[SubjectScore]


class RIASECScore(BaseModel):
    """Điểm từng nhóm RIASEC của học sinh"""
    R: float = 0.0
    I: float = 0.0
    A: float = 0.0
    S: float = 0.0
    E: float = 0.0
    C: float = 0.0
    top_code: str            # VD: "RIA", "ISA"


# ============================================================
# REQUEST SCHEMAS — Next.js gửi lên
# ============================================================
class StudentProfileRequest(BaseModel):
    riasec_scores: RIASECScore
    # Key là subject_code từ DB: MATH, PHYSICS, CHEMISTRY...
    subject_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Key: subject_code (MATH, PHYSICS,...) | Value: điểm 0.0–10.0",
        example={
            "MATH": 8.5,
            "PHYSICS": 7.0,
            "ENGLISH": 9.0,
        }
    )
    province_id: Optional[str] = None
    district_id: Optional[str] = None
    admission_year: int = 2026
    top_n: int = Field(default=10, ge=1, le=50)


# ============================================================
# RESPONSE SCHEMAS — API trả về cho Next.js
# ============================================================

class DimensionBreakdown(BaseModel):
    """Chi tiết điểm từng chiều đánh giá — dùng cho Explainability"""
    label: str               # VD: "Định hướng nghề nghiệp"
    score: float             # Điểm thành phần [0, 1]
    weight: float            # Trọng số
    contribution: float      # score × weight
    explanation: str         # Câu giải thích cho học sinh


class BestAdmissionPath(BaseModel):
    """Con đường xét tuyển tốt nhất cho một ngành tại một trường"""
    institution_id: UUID
    institution_name: str
    campus_id: UUID
    combination_code: str    # VD: "A00"
    student_score: float     # Tổng điểm học sinh theo tổ hợp này
    cutoff_score: float      # Điểm chuẩn năm gần nhất
    safety_margin: float     # student_score - cutoff_score


class MajorRecommendation(BaseModel):
    """Một ngành được gợi ý — đơn vị kết quả cơ bản"""
    major_id: UUID
    major_code: str | None
    major_name_vi: str | None
    major_name_en: str | None
    field_name_vi: str | None      # Lĩnh vực (VD: "Kỹ thuật - Công nghệ")
    group_name_vi: str | None      # Nhóm ngành

    # Điểm xếp hạng tổng hợp [0, 1]
    final_score: float

    # RIASEC khớp với ngành (%)
    riasec_match_percent: float

    # Con đường xét tuyển tốt nhất
    best_paths: list[BestAdmissionPath]

    # Explainability — chỉ có ở Baseline 4
    dimensions: Optional[list[DimensionBreakdown]] = None
    primary_reason: Optional[str] = None


class RecommendationResponse(BaseModel):
    """
    Response chuẩn trả về cho mọi baseline.
    Giúp Next.js dùng cùng một interface cho cả 4 baseline.
    """
    baseline: str            # "random" | "content_based" | "hybrid_fixed" | "proposed"
    riasec_code: str         # Mã Holland top 3 VD: "RIA"
    total_candidates: int    # Tổng số ngành tìm được trước khi xếp hạng
    results: list[MajorRecommendation]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str