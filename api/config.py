"""应用配置"""
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://gan:password@localhost:5432/globalautonews"
)
PAGE_SIZE = 20
MAX_PAGE_SIZE = 100