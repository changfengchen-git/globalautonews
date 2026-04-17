"""
GlobalAutoNews API - 主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import articles, sources, health, candidates, events

app = FastAPI(
    title="GlobalAutoNews API",
    description="全球汽车新闻监控与聚合系统 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router, prefix="/api", tags=["Articles"])
app.include_router(sources.router, prefix="/api", tags=["Sources"])
app.include_router(candidates.router, prefix="/api", tags=["Candidates"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(health.router, prefix="/api", tags=["Health"])


@app.get("/")
async def root():
    return {
        "name": "GlobalAutoNews API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }