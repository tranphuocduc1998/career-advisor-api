# app/routers/baseline4.py

from fastapi import APIRouter, HTTPException
from app.services.proposed_method import run_proposed_method, get_optimal_weights
from app.models.schemas import RecommendationResponse
from pydantic import BaseModel, Field
from typing import Optional


class ProposedMethodRequest(BaseModel):
    """Request body cho Baseline 4"""

    top_code: str = Field(
        default="RIA",
        min_length=1,
        max_length=6,
        description="Mã Holland top 3 (VD: RIA, ISA)",
        example="RIA",
    )
    student_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Điểm từng môn theo subject_code",
        example={
            "MATH": 8.5,
            "PHYSICS": 7.0,
            "ENGLISH": 9.0,
        },
    )
    admission_year: int = Field(
        default=2026,
        description="Năm tuyển sinh",
    )
    top_n: int = Field(
        default=3,          # Dùng K tối ưu làm mặc định
        ge=1,
        le=50,
        description="Số ngành muốn gợi ý (mặc định K tối ưu = 3)",
    )
    province_id: Optional[str] = Field(
        default=None,
        description="ID tỉnh/thành (tuỳ chọn)",
    )
    district_id: Optional[str] = Field(
        default=None,
        description="ID quận/huyện (tuỳ chọn)",
    )


router = APIRouter(
    prefix="/api/v1/baseline4",
    tags=["Baseline 4 — Proposed Method (Optimal Weights + Explainability)"],
)


@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Proposed Method — Trọng số tối ưu + Giải thích",
    description="""
    Gợi ý ngành theo Proposed Method với 2 cải tiến so với Baseline 3:

    **1. Trọng số tối ưu từ Grid Search:**

    FinalScore = α·RIASEC + β·Subject + γ·Safety + δ·Geo

    Với α=0.7, β=0.1, γ=0.1, δ=0.1 (tìm bởi Grid Search, K=3)

    **2. Explainability đầy đủ:**
    - Điểm từng chiều (score, weight, contribution)
    - Key factor — chiều ảnh hưởng nhiều nhất
    - Câu giải thích ngôn ngữ tự nhiên
    """,
)
async def proposed_method_recommend(request: ProposedMethodRequest):

    # Chuẩn hoá top_code
    clean_code = "".join(
        c for c in request.top_code.upper() if c in "RIASEC"
    )[:3]

    if not clean_code:
        raise HTTPException(
            status_code=400,
            detail="top_code không hợp lệ. Chỉ chấp nhận R, I, A, S, E, C (VD: RIA)",
        )

    # Validate điểm môn
    for subject, score in request.student_scores.items():
        if not (0.0 <= score <= 10.0):
            raise HTTPException(
                status_code=400,
                detail=f"Điểm môn {subject} phải trong khoảng 0.0–10.0, nhận được {score}",
            )

    return await run_proposed_method(
        top_code=clean_code,
        student_scores=request.student_scores,
        admission_year=request.admission_year,
        top_n=request.top_n,
        province_id=request.province_id,
        district_id=request.district_id,
    )


@router.get(
    "/weights",
    summary="Xem trọng số tối ưu hiện tại",
    description="Trả về bộ trọng số tối ưu đang được dùng trong Baseline 4.",
    tags=["Baseline 4 — Proposed Method (Optimal Weights + Explainability)"],
)
async def get_weights():
    """
    Endpoint phụ — xem trọng số tối ưu.
    Dùng để kiểm tra và hiển thị trong báo cáo đồ án.
    """
    weights = get_optimal_weights()
    return {
        "source": "grid_search",
        "weights": {
            "alpha": weights["alpha"],
            "beta":  weights["beta"],
            "gamma": weights["gamma"],
            "delta": weights["delta"],
        },
        "optimal_k": weights["k"],
        "formula": (
            f"FinalScore = {weights['alpha']}·RIASEC "
            f"+ {weights['beta']}·Subject "
            f"+ {weights['gamma']}·Safety "
            f"+ {weights['delta']}·Geo"
        ),
    }