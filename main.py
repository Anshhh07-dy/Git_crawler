"""
FastAPI application.

Endpoints:
  POST /api/crawl-jobs           -> start a new crawl job
  GET  /api/crawl-jobs/{id}       -> job status + stats
  GET  /api/crawl-jobs/{id}/log   -> crawl trace (log entries)
  GET  /api/crawl-jobs/{id}/resources -> resources found (filterable, searchable)
  GET  /api/crawl-jobs/{id}/graph -> knowledge graph edges
  GET  /api/crawl-jobs/{id}/categories -> category counts for filter sidebar
  GET  /api/search               -> search across ALL jobs' resources
  GET  /                          -> serves the frontend
"""
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_

from app.core.db import (
    init_db, SessionLocal, CrawlJob, CrawlLogEntry, Resource, ResourceRelation,
    ResourceCategory, new_id,
)
from app.core.crawler import run_crawl_job

app = FastAPI(title="Resource Discovery & Intelligence Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CrawlJobCreate(BaseModel):
    seed_url: str
    max_depth: int = Field(default=2, ge=0, le=4)
    max_pages: int = Field(default=60, ge=1, le=300)


class CrawlJobOut(BaseModel):
    id: str
    seed_url: str
    status: str
    max_depth: int
    max_pages: int
    pages_visited: int
    resources_found: int
    duplicates_removed: int
    error: str | None = None

    class Config:
        from_attributes = True


class LogEntryOut(BaseModel):
    depth: int
    status: str
    url: str
    note: str

    class Config:
        from_attributes = True


class ResourceOut(BaseModel):
    id: str
    title: str
    description: str | None
    category: str
    url: str
    domain: str
    quality_score: float
    authority_score: float
    freshness_score: float
    popularity_score: float
    tags: list[str]
    extra: dict

    class Config:
        from_attributes = True

    @classmethod
    def from_resource(cls, r: Resource):
        return cls(
            id=r.id, title=r.title, description=r.description,
            category=r.category.value if hasattr(r.category, "value") else r.category,
            url=r.url, domain=r.domain,
            quality_score=r.quality_score, authority_score=r.authority_score,
            freshness_score=r.freshness_score, popularity_score=r.popularity_score,
            tags=r.tags or [], extra=r.extra or {},
        )


class GraphEdgeOut(BaseModel):
    source_title: str
    source_id: str
    target_title: str
    target_id: str
    relation_type: str


# ---------------------------------------------------------------------------
# Crawl job endpoints
# ---------------------------------------------------------------------------

@app.post("/api/crawl-jobs", response_model=CrawlJobOut)
def create_crawl_job(payload: CrawlJobCreate, background_tasks: BackgroundTasks):
    if not payload.seed_url.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(400, "seed_url must start with http:// or https://")

    db = SessionLocal()
    try:
        job = CrawlJob(
            id=new_id(),
            seed_url=payload.seed_url.strip(),
            status="pending",
            max_depth=payload.max_depth,
            max_pages=payload.max_pages,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        background_tasks.add_task(run_crawl_job, job.id)

        return CrawlJobOut.model_validate(job)
    finally:
        db.close()


@app.get("/api/crawl-jobs/{job_id}", response_model=CrawlJobOut)
def get_crawl_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if not job:
            raise HTTPException(404, "Job not found")
        return CrawlJobOut.model_validate(job)
    finally:
        db.close()


@app.get("/api/crawl-jobs/{job_id}/log", response_model=list[LogEntryOut])
def get_crawl_log(job_id: str, limit: int = Query(default=200, le=1000)):
    db = SessionLocal()
    try:
        entries = (
            db.query(CrawlLogEntry)
            .filter(CrawlLogEntry.job_id == job_id)
            .order_by(CrawlLogEntry.created_at.asc())
            .limit(limit)
            .all()
        )
        return [LogEntryOut.model_validate(e) for e in entries]
    finally:
        db.close()


@app.get("/api/crawl-jobs/{job_id}/resources", response_model=list[ResourceOut])
def get_job_resources(
    job_id: str,
    category: str | None = None,
    q: str | None = None,
    min_score: float = 0.0,
    limit: int = Query(default=100, le=500),
):
    db = SessionLocal()
    try:
        query = db.query(Resource).filter(
            Resource.job_id == job_id,
            Resource.is_duplicate == False,  # noqa: E712
            Resource.quality_score >= min_score,
        )

        if category:
            try:
                cat_enum = ResourceCategory(category)
                query = query.filter(Resource.category == cat_enum)
            except ValueError:
                raise HTTPException(400, f"Unknown category: {category}")

        if q:
            like = f"%{q.lower()}%"
            query = query.filter(
                or_(
                    Resource.title.ilike(like),
                    Resource.description.ilike(like),
                    Resource.url.ilike(like),
                )
            )

        results = query.order_by(Resource.quality_score.desc()).limit(limit).all()
        return [ResourceOut.from_resource(r) for r in results]
    finally:
        db.close()


@app.get("/api/crawl-jobs/{job_id}/categories")
def get_category_counts(job_id: str):
    db = SessionLocal()
    try:
        resources = (
            db.query(Resource)
            .filter(Resource.job_id == job_id, Resource.is_duplicate == False)  # noqa: E712
            .all()
        )
        counts: dict[str, int] = {}
        for r in resources:
            cat = r.category.value if hasattr(r.category, "value") else r.category
            counts[cat] = counts.get(cat, 0) + 1
        return counts
    finally:
        db.close()


@app.get("/api/crawl-jobs/{job_id}/graph", response_model=list[GraphEdgeOut])
def get_job_graph(job_id: str, limit: int = Query(default=50, le=300)):
    db = SessionLocal()
    try:
        edges = (
            db.query(ResourceRelation)
            .filter(ResourceRelation.job_id == job_id)
            .limit(limit)
            .all()
        )
        out = []
        for e in edges:
            source = db.query(Resource).filter(Resource.id == e.source_id).first()
            target = db.query(Resource).filter(Resource.id == e.target_id).first()
            if not source or not target:
                continue
            out.append(GraphEdgeOut(
                source_title=source.title, source_id=source.id,
                target_title=target.title, target_id=target.id,
                relation_type=e.relation_type,
            ))
        return out
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Global search (across all completed jobs)
# ---------------------------------------------------------------------------

@app.get("/api/search", response_model=list[ResourceOut])
def global_search(
    q: str = Query(..., min_length=1),
    category: str | None = None,
    limit: int = Query(default=50, le=200),
):
    db = SessionLocal()
    try:
        query = db.query(Resource).filter(Resource.is_duplicate == False)  # noqa: E712

        if category:
            try:
                cat_enum = ResourceCategory(category)
                query = query.filter(Resource.category == cat_enum)
            except ValueError:
                raise HTTPException(400, f"Unknown category: {category}")

        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                Resource.title.ilike(like),
                Resource.description.ilike(like),
                Resource.url.ilike(like),
                Resource.domain.ilike(like),
            )
        )

        results = query.order_by(Resource.quality_score.desc()).limit(limit).all()
        return [ResourceOut.from_resource(r) for r in results]
    finally:
        db.close()


@app.get("/api/crawl-jobs", response_model=list[CrawlJobOut])
def list_crawl_jobs(limit: int = Query(default=20, le=100)):
    db = SessionLocal()
    try:
        jobs = db.query(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(limit).all()
        return [CrawlJobOut.model_validate(j) for j in jobs]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Frontend (static files)
# ---------------------------------------------------------------------------

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/")
    def serve_index():
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Resource Discovery Engine API. POST /api/crawl-jobs to start a crawl."}
