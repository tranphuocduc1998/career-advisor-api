# app/routers/baseline2.py

from fastapi import APIRouter, Query
from typing import Optional
from app.services.content_based import run_content_based
from app.models.schemas import RecommendationResponse

router = APIRouter(
    prefix="/api/v1/baseline2",
    tags=["Baseline 2 — Content-Based (Holland Only)"],
)

@router.get(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Content-Based Filtering — Holland Only",
    description="""
    Gợi ý ngành dựa thuần túy trên mã Holland RIASEC của học sinh.
    Xếp hạng theo Weighted Match Score — nhóm Holland #1 được ưu tiên hơn #2, #3.
    Không dùng điểm số hay địa lý để xếp hạng.
    """,
)
async def content_based_recommend(
    top_code: str = Query(
        default="RIA",
        min_length=1,
        max_length=6,
        description="Mã Holland top 3 từ kết quả test (VD: RIA, ISA, ECR)",
    ),
    admission_year: int = Query(
        default=2026,
        description="Năm tuyển sinh",
    ),
    top_n: int = Query(
        default=5,
        ge=1,
        le=50,
        description="Số ngành muốn gợi ý",
    ),
    province_id: Optional[str] = Query(
        default=None,
        description="ID tỉnh/thành (tuỳ chọn)",
    ),
    district_id: Optional[str] = Query(
        default=None,
        description="ID quận/huyện (tuỳ chọn)",
    ),
):
    # Chuẩn hoá top_code — uppercase, bỏ ký tự lạ
    clean_code = "".join(
        c for c in top_code.upper() if c in "RIASEC"
    )[:3]

    if not clean_code:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="top_code không hợp lệ. Chỉ chấp nhận các ký tự R, I, A, S, E, C (VD: RIA)"
        )

    return await run_content_based(
        top_code=clean_code,
        admission_year=admission_year,
        top_n=top_n,
        province_id=province_id,
        district_id=district_id,
    )