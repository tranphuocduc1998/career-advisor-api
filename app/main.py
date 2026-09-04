from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.connection import get_pool, close_pool
from app.models.schemas import HealthResponse
from app.config import ALLOWED_ORIGINS

# Thêm vào phần import ở đầu file
from app.routers import baseline1

app = FastAPI(title="Career Advisor API", version="1.0.0")

# CORS — cho phép Next.js gọi vào API
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,      # Đọc từ .env, không hard-code
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi động pool khi app start
@app.on_event("startup")
async def startup():
    await get_pool()
    print(f"✅ Database pool created")
    print(f"✅ Allowed origins: {ALLOWED_ORIGINS}")

# Đóng pool khi app tắt
@app.on_event("shutdown")
async def shutdown():
    await close_pool()
    print("Database pool closed")

# Health check endpoint — dùng để kiểm tra API còn sống không
@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthResponse(status="ok", database=db_status)

# Thêm vào sau phần khai báo middleware CORS
app.include_router(baseline1.router)
