"""API 数据库连接"""
from shared.database import get_engine, get_session_factory
from api.config import DATABASE_URL

engine = get_engine(DATABASE_URL)
SessionFactory = get_session_factory(engine)

async def get_db():
    """FastAPI 依赖注入用的 database session"""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise