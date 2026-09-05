# run_grid_search.py
# Chạy 1 lần để tìm trọng số tối ưu
# Sau đó Baseline 4 đọc kết quả từ file JSON

import asyncio
from app.services.grid_search import run_grid_search

if __name__ == "__main__":
    asyncio.run(run_grid_search())