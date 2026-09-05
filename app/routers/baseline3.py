# app/routers/baseline3.py

from fastapi import APIRouter, HTTPException
from app.services.hybrid_fixed import run_hybrid_fixed
from app.models.schemas import RecommendationResponse
from pydantic import BaseModel, Field
from typing import Optional


class HybridFixedRequest(BaseModel):
    """Request body cho Baseline 3"""

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
        default=5,
        ge=1,
        le=50,
        description="Số ngành muốn gợi ý",
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
    prefix="/api/v1/baseline3",
    tags=["Baseline 3 — Hybrid Fixed Weights"],
)


@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Hybrid Fixed Weights",
    description="""
    Gợi ý ngành theo công thức hybrid kết hợp 4 yếu tố với trọng số cố định:

    **FinalScore = 0.40·RIASEC + 0.25·Subject + 0.25·Safety + 0.10·Geo**

    - **RIASEC** : Mức độ khớp mã Holland (Weighted Match Score)
    - **Subject** : Điểm tổ hợp môn tốt nhất của học sinh (normalize 0–1)
    - **Safety**  : Biên an toàn so với điểm chuẩn (clip 0–1, range=5đ)
    - **Geo**     : Mức độ khớp địa lý (0 / 0.5 / 1.0)

    Chỉ trả về ngành học sinh **đủ điểm chuẩn** ít nhất 1 tổ hợp.
    """,
)
async def hybrid_fixed_recommend(request: HybridFixedRequest):

    # Chuẩn hoá top_code
    clean_code = "".join(
        c for c in request.top_code.upper() if c in "RIASEC"
    )[:3]

    if not clean_code:
        raise HTTPException(
            status_code=400,
            detail="top_code không hợp lệ. Chỉ chấp nhận R, I, A, S, E, C (VD: RIA)",
        )

    # Validate điểm môn học
    for subject, score in request.student_scores.items():
        if not (0.0 <= score <= 10.0):
            raise HTTPException(
                status_code=400,
                detail=f"Điểm môn {subject} phải trong khoảng 0.0 – 10.0, nhận được {score}",
            )

    return await run_hybrid_fixed(
        top_code=clean_code,
        student_scores=request.student_scores,
        admission_year=request.admission_year,
        top_n=request.top_n,
        province_id=request.province_id,
        district_id=request.district_id,
    )