"""
Database models and session management.
Uses SQLite for zero-config local running — swap DATABASE_URL for
Postgres in production without changing any model code.
"""
import os
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, String, Text, Float, DateTime, ForeignKey,
    JSON, Integer, Boolean, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/engine.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def new_id() -> str:
    return str(uuid.uuid4())


class ResourceCategory(str, enum.Enum):
    RESEARCH_PAPER = "research_paper"
    DATASET = "dataset"
    API = "api"
    OPEN_SOURCE_TOOL = "open_source_tool"
    SCHOLARSHIP = "scholarship"
    FELLOWSHIP = "fellowship"
    INTERNSHIP = "internship"
    COMPETITION = "competition"
    GRANT = "grant"
    COURSE = "course"
    LEARNING_RESOURCE = "learning_resource"
    DOCUMENTATION = "documentation"
    COMMUNITY = "community"
    STARTUP = "startup"
    FUNDING = "funding"
    GOV_SCHEME = "gov_scheme"
    UNKNOWN = "unknown"


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id = Column(String, primary_key=True, default=new_id)
    seed_url = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending|running|done|failed
    max_depth = Column(Integer, default=2)
    max_pages = Column(Integer, default=60)
    pages_visited = Column(Integer, default=0)
    resources_found = Column(Integer, default=0)
    duplicates_removed = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    pages = relationship("Page", back_populates="job", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="job", cascade="all, delete-orphan")
    log_entries = relationship("CrawlLogEntry", back_populates="job", cascade="all, delete-orphan")


class CrawlLogEntry(Base):
    """A single event in the crawl trace — used to render the live log in the UI."""
    __tablename__ = "crawl_log_entries"

    id = Column(String, primary_key=True, default=new_id)
    job_id = Column(String, ForeignKey("crawl_jobs.id"), index=True)
    depth = Column(Integer, default=0)
    status = Column(String, default="found")  # seed|found|skip|error
    url = Column(String)
    note = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("CrawlJob", back_populates="log_entries")


class Page(Base):
    __tablename__ = "pages"

    id = Column(String, primary_key=True, default=new_id)
    job_id = Column(String, ForeignKey("crawl_jobs.id"), index=True)
    url = Column(String, index=True)
    title = Column(String, nullable=True)
    cleaned_content = Column(Text, nullable=True)
    content_hash = Column(String, index=True, nullable=True)
    depth = Column(Integer, default=0)
    parent_url = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    source_type = Column(String, default="web")  # web|github_repo|github_file
    crawled_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("CrawlJob", back_populates="pages")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True, default=new_id)
    job_id = Column(String, ForeignKey("crawl_jobs.id"), index=True)
    page_id = Column(String, ForeignKey("pages.id"), nullable=True)

    title = Column(String)
    description = Column(Text)
    category = Column(SAEnum(ResourceCategory), index=True, default=ResourceCategory.UNKNOWN)
    url = Column(String, index=True)
    domain = Column(String, index=True)

    quality_score = Column(Float, default=0.0)
    authority_score = Column(Float, default=0.0)
    freshness_score = Column(Float, default=0.0)
    popularity_score = Column(Float, default=0.0)

    tags = Column(JSON, default=list)
    extra = Column(JSON, default=dict)  # arbitrary metadata: stars, deadlines, provider, etc.

    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(String, ForeignKey("resources.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("CrawlJob", back_populates="resources")


class ResourceRelation(Base):
    """Edges in the knowledge graph: source -> relation -> target."""
    __tablename__ = "resource_relations"

    id = Column(String, primary_key=True, default=new_id)
    job_id = Column(String, ForeignKey("crawl_jobs.id"), index=True)
    source_id = Column(String, ForeignKey("resources.id"))
    target_id = Column(String, ForeignKey("resources.id"))
    relation_type = Column(String)  # documents|uses|discusses|offered_by|funds|related_to


def init_db():
    os.makedirs("./data", exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
