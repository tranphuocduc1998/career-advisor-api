# app/routers/baseline1.py

from fastapi import APIRouter, Query
from uuid import UUID
from typing import Optional
from app.services.random_recommender import run_random_recommender
from app.models.schemas import RecommendationResponse

router = APIRouter(
    prefix="/api/v1/baseline1",
    tags=["Baseline 1 — Random Recommender"],
)

@router.get(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Random Recommender",
    description="""
    Gợi ý ngành hoàn toàn ngẫu nhiên từ danh sách ngành đang tuyển sinh.
    Dùng làm mốc so sánh tối thiểu (lower bound) cho các baseline khác.
    """,
)
async def random_recommend(
    admission_year: int = Query(default=2026, description="Năm tuyển sinh"),
    top_n: int = Query(default=5, ge=1, le=50, description="Số ngành muốn gợi ý"),
    province_id: Optional[UUID] = Query(default=None, description="ID tỉnh/thành (tuỳ chọn)"),
    district_id: Optional[UUID] = Query(default=None, description="ID quận/huyện (tuỳ chọn)"),
):
    return await run_random_recommender(
        admission_year=admission_year,
        top_n=top_n,
        province_id=province_id,
        district_id=district_id,
    )