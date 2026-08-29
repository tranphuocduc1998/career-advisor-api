import asyncpg
from app.config import DATABASE_URL

# Pool kết nối dùng chung — tạo 1 lần khi app khởi động
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=5,
            ssl="require"          # Aiven yêu cầu SSL
        )
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None