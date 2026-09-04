# app/db/data_loader.py

from app.db.connection import get_pool
from app.db import queries
from uuid import UUID
from typing import Optional


async def load_eligible_majors(
    admission_year: int,
    province_id: Optional[UUID] = None,
    district_id: Optional[UUID] = None,
) -> list[dict]:
    """
    Lấy toàn bộ ngành hợp lệ từ DB.
    Query động — ghép thêm điều kiện địa lý nếu có.
    """
    pool = await get_pool()

    sql = queries.GET_ELIGIBLE_MAJORS
    params: list = [admission_year]

    if province_id:
        sql += queries.GEO_FILTER_PROVINCE
        params.append(province_id)

        if district_id:
            sql += queries.GEO_FILTER_DISTRICT
            params.append(district_id)

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]


async def load_major_riasec() -> list[dict]:
    """Lấy mapping RIASEC của tất cả ngành — dùng cho Baseline 2, 3, 4"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(queries.GET_MAJOR_RIASEC)
        return [dict(row) for row in rows]


async def load_combination_subjects() -> list[dict]:
    """Lấy danh sách môn học trong từng tổ hợp — dùng cho Baseline 2, 3, 4"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(queries.GET_COMBINATION_SUBJECTS)
        return [dict(row) for row in rows]