"""
候选源审批 API 路由
"""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from shared.models import SourceCandidate, Source

router = APIRouter(prefix="/candidates", tags=["candidates"])


class CandidateResponse(BaseModel):
    id: int
    domain: str
    url: Optional[str]
    mention_count: int
    status: str
    auto_analysis: Optional[dict]
    discovered_from: Optional[list]
    first_mentioned_at: Optional[datetime]
    last_mentioned_at: Optional[datetime]
    analyzed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CandidateListResponse(BaseModel):
    items: List[CandidateResponse]
    total: int
    page: int
    limit: int


class ApproveRequest(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    language: Optional[str] = None
    priority: str = "medium"


class ApproveResponse(BaseModel):
    success: bool
    source_id: int
    message: str


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    获取候选源列表（按 mention_count 排序）
    """
    query = select(SourceCandidate)

    if status:
        query = query.where(SourceCandidate.status == status)

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页查询
    query = query.order_by(SourceCandidate.mention_count.desc())
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    candidates = result.scalars().all()

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取候选源详情（含 auto_analysis）
    """
    result = await db.execute(
        select(SourceCandidate).where(SourceCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return CandidateResponse.model_validate(candidate)


@router.post("/{candidate_id}/approve", response_model=ApproveResponse)
async def approve_candidate(
    candidate_id: int,
    request: ApproveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批准候选源（创建 source 记录，状态设为 active）
    """
    # 获取候选源
    result = await db.execute(
        select(SourceCandidate).where(SourceCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status == "approved":
        raise HTTPException(status_code=400, detail="Candidate already approved")

    # 检查是否已存在同域名的 source
    existing_source = await db.execute(
        select(Source).where(Source.domain == candidate.domain)
    )
    if existing_source.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Source with this domain already exists")

    # 从 auto_analysis 获取信息
    analysis = candidate.auto_analysis or {}

    # 创建新的 Source 记录
    source = Source(
        name=request.name or candidate.domain,
        domain=candidate.domain,
        url=candidate.url or f"https://{candidate.domain}",
        country=request.country or analysis.get("country", "US"),
        language=request.language or analysis.get("language", "en"),
        priority=request.priority,
        status="active",
        tier=1,
        has_rss=False,
        crawl_interval_minutes=240,
        next_crawl_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    db.add(source)
    await db.flush()

    # 更新候选源状态
    candidate.status = "approved"
    candidate.approved_at = datetime.now(timezone.utc)
    candidate.approved_source_id = source.id

    await db.commit()

    return ApproveResponse(
        success=True,
        source_id=source.id,
        message=f"Source '{source.name}' created successfully",
    )


@router.post("/{candidate_id}/reject", response_model=ApproveResponse)
async def reject_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    拒绝候选源
    """
    result = await db.execute(
        select(SourceCandidate).where(SourceCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status == "rejected":
        raise HTTPException(status_code=400, detail="Candidate already rejected")

    # 更新状态
    candidate.status = "rejected"
    candidate.rejected_at = datetime.now(timezone.utc)

    await db.commit()

    return ApproveResponse(
        success=True,
        source_id=0,
        message=f"Candidate '{candidate.domain}' rejected",
    )
