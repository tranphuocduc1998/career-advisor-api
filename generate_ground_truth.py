# generate_ground_truth.py
# Chạy 1 lần để sinh ground truth dataset
# Sau đó Grid Search đọc file này — không cần chạy lại

import asyncio
from app.services.ground_truth import generate_and_save_ground_truth

if __name__ == "__main__":
    asyncio.run(generate_and_save_ground_truth())