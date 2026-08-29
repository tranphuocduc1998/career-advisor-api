from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.connection import get_pool, close_pool

app = FastAPI(title="Career Advisor API", version="1.0.0")

# CORS — cho phép Next.js gọi vào API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Thêm domain production sau
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi động pool khi app start
@app.on_event("startup")
async def startup():
    await get_pool()
    print("Database pool created")

# Đóng pool khi app tắt
@app.on_event("shutdown")
async def shutdown():
    await close_pool()
    print("Database pool closed")

# Health check endpoint — dùng để kiểm tra API còn sống không
@app.get("/health")
async def health():
    return {"status": "ok"}