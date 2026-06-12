# Resource Discovery & Intelligence Engine
Git_crawler

Resource Discovery & Intelligence Engine

Turn any GitHub repository, documentation portal, awesome-list, university resource page, scholarship directory, research project, or general website into a structured knowledge graph of opportunities, learning resources, datasets, APIs, certifications, tools, and hidden links.

Git_crawler is an open-source resource discovery engine that recursively crawls repositories and websites, extracts relevant resources, classifies them into meaningful categories, scores their quality, removes duplicates, and builds a searchable knowledge graph.

Instead of manually browsing hundreds of pages and links, Git_crawler automatically discovers what is hidden inside them.

Why This Project Exists

The internet contains millions of valuable resources.

The problem is not a lack of information.

The problem is discovery.

A single GitHub repository may contain:

- Documentation
- Datasets
- APIs
- Tutorials
- Courses
- Research papers
- Scholarships
- Funding opportunities
- Community links
- Related repositories

Most users only see the repository homepage and never discover the ecosystem surrounding it.

Git_crawler was built to solve this problem.

Give it a starting URL and it will recursively explore the surrounding ecosystem, extract valuable resources, classify them, score them, deduplicate them, and organize them into a structured knowledge graph.

The project was originally designed as part of the infrastructure behind SkillMap, a platform focused on helping students discover opportunities, learning paths, certifications, scholarships, research resources, and career growth tools.


What Can It Discover?

Git_crawler can identify and organize:

Learning Resources

- Courses
- Tutorials
- Documentation
- Learning paths
- Educational videos

Career Opportunities

- Scholarships
- Fellowships
- Grants
- Internships
- Job boards

Research Resources

- Research papers
- Datasets
- Open research projects
- Academic tools

Developer Resources

- APIs
- SDKs
- Open-source projects
- Libraries
- Frameworks

AI Resources

- LLM APIs
- AI tools
- AI datasets
- AI frameworks
- Model repositories

Communities

- Discord servers
- Forums
- Slack communities
- Developer groups

---

Example

Input:

https://github.com/ourresearch/OpenAlex

Output:

✓ Research papers discovered

✓ Dataset repositories discovered

✓ Documentation pages extracted

✓ API references indexed

✓ Related repositories found

✓ Knowledge graph generated

Core Features

Recursive Crawling

Starting from a single URL, the engine explores connected pages and repositories while respecting configurable limits.

GitHub Intelligence

Special handling for GitHub repositories:

- Repository metadata
- README parsing
- Repository popularity
- Stars and forks
- Related resources

Smart Classification

Resources are automatically classified into categories using heuristic rules.

Optional LLM-assisted classification is available for ambiguous pages.

Resource Scoring

Every resource receives a quality score based on:

- Authority
- Popularity
- Freshness
- Confidence
- Source reputation

Deduplication Engine

Removes:

- Duplicate URLs
- Content duplicates
- Near-duplicate resources

This prevents noisy results and improves search quality.

Knowledge Graph Generation

Builds relationships between resources:

- Documents
- Repositories
- APIs
- Courses
- Datasets
- Organizations

Resulting in a graph that can be visualized and searched.

Search Engine

Search across all discovered resources with filters for:

- Categories
- Minimum score
- Keywords
- Crawl jobs

Architecture

Seed URL
↓
Fetch Content
↓
Extract Links
↓
Classify Resources
↓
Score Quality
↓
Deduplicate Results
↓
Store Resources
↓
Generate Knowledge Graph
↓
Search & Visualization

Tech Stack

Backend

- FastAPI
- Python
- SQLAlchemy
- HTTPX
- BeautifulSoup

Database

- SQLite (default)
- PostgreSQL (production-ready)

AI

- Anthropic Claude (optional)

Infrastructure

- Docker
- Docker Compose

Frontend

- React
- Vanilla JavaScript
- Graph Visualization


Quick Start

Docker (Recommended)

docker compose up --build

Open:

http://localhost:8000

---

Local Installation

pip install -r requirements.txt
uvicorn app.main:app --reload

Open:

http://localhost:8000

Environment Variables

GitHub Token

Provides higher API limits.

export GITHUB_TOKEN=ghp_xxxxx

Rate Limit:

- Authenticated: 5000 requests/hour
- Unauthenticated: 60 requests/hour

Anthropic API Key

Optional.

Enables LLM-assisted classification.

export ANTHROPIC_API_KEY=sk-ant-xxxxx

Example Crawl Targets

Research

OpenAlex

- Research metadata
- Citation graphs
- Academic datasets

Awesome Lists

Awesome repositories containing:

- Courses
- APIs
- Learning resources
- Developer tools

University Websites

Discover:

- Scholarships
- Fellowships
- Research programs
- Funding opportunities

Documentation Portals

Extract:

- Guides
- Tutorials
- APIs
- Learning paths

API Endpoints

Create Crawl Job

POST /api/crawl-jobs

Job Status

GET /api/crawl-jobs/{id}

Crawl Logs

GET /api/crawl-jobs/{id}/log

Resources

GET /api/crawl-jobs/{id}/resources

Categories

GET /api/crawl-jobs/{id}/categories

Knowledge Graph

GET /api/crawl-jobs/{id}/graph

Search

GET /api/search?q=keyword

Scaling To Production

This repository ships as a local-first implementation.

The architecture was intentionally designed to scale.

Database

Development:

SQLite

Production:

PostgreSQL

Task Queue

Development:

In-memory queue

Production:

Redis + Celery

Fetching

Development:

HTTPX + BeautifulSoup

Production:

Playwright / Crawl4AI

Search

Development:

SQLite queries

Production:

Meilisearch
ElasticSearch
PostgreSQL Full Text Search

Deduplication

Development:

Token similarity

Production:

Embedding similarity
pgvector

Potential Use Cases

- Opportunity aggregation platforms
- Scholarship search engines
- Research discovery systems
- Knowledge graph generation
- AI resource indexing
- Learning recommendation systems
- Developer search engines
- Educational technology products
- Community discovery platforms

Contributing

Contributions are welcome.

Areas where help is needed:

- Better classification models
- New resource categories
- Search improvements
- Graph visualizations
- Playwright integration
- Embedding-based deduplication
- Documentation improvements
- UI/UX enhancements

If you're looking for a first contribution, check issues labeled:

- good first issue
- help wanted
- enhancement

Roadmap

Phase 1

- Resource discovery
- Classification
- Deduplication
- Search

Phase 2

- PostgreSQL migration
- Redis queues
- Distributed crawling

Phase 3

- Semantic search
- Embedding-based ranking
- Recommendation engine

Phase 4

- Multi-source intelligence graph
- Real-time crawling
- Opportunity prediction
- Personalized recommendations

Vision

The long-term goal is to create an open-source discovery engine capable of mapping the hidden educational, research, career, and developer ecosystems of the internet.

A search engine does not just index pages.

It discovers connections.

Git_crawler aims to discover those connections and make them accessible to everyone.

Built by Ansh Dubey.

## Run it

### Option A — Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8000

### Option B — Direct (no Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000

## Optional environment variables

```bash
# Higher GitHub API rate limit (5000/hr vs 60/hr unauthenticated)
export GITHUB_TOKEN=ghp_xxxxx

# Enables LLM-assisted classification for ambiguous pages
# (heuristic classifier works fully without this — it's an upgrade, not a requirement)
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

With docker-compose, put these in a `.env` file in the project root:

```
GITHUB_TOKEN=ghp_xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## How it works

```
Seed URL
  -> is it a GitHub repo? -> GitHub API: repo metadata + README (markdown links)
  -> otherwise            -> HTTP fetch + BeautifulSoup: HTML links + text content
  -> classify content (heuristic keyword rules, optional LLM fallback)
  -> score (authority / freshness / popularity / confidence)
  -> deduplicate (exact URL, content hash, near-duplicate title overlap)
  -> store as Resource
  -> recurse into discovered links (up to max_depth / max_pages)
  -> after crawl: derive knowledge graph edges (documents / links_to)
```

Try it with:
- `https://github.com/ourresearch/OpenAlex` — research API + docs + datasets
- `https://github.com/cheahjs/free-llm-api-resources` — awesome-list of APIs
- Any university scholarships page, docs portal, etc.

## Project structure

```
app/
  main.py            FastAPI app + all API endpoints
  core/
    db.py            SQLAlchemy models (SQLite by default)
    links.py         URL normalization, link/markdown extraction
    fetcher.py       HTTP fetch + content extraction (httpx + BeautifulSoup)
    github_client.py GitHub API client (repo metadata, README)
    classifier.py    Heuristic classification (+ optional LLM upgrade)
    scoring.py       Quality/authority/freshness/popularity scoring
    dedup.py         Exact + near-duplicate detection
    graph.py         Knowledge graph relation extraction
    crawler.py       Orchestrates the full recursive pipeline
  static/
    index.html       Frontend (React via CDN, no build step)
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/crawl-jobs` | Start a crawl (`{seed_url, max_depth, max_pages}`) |
| GET | `/api/crawl-jobs/{id}` | Job status + stats |
| GET | `/api/crawl-jobs/{id}/log` | Crawl trace log |
| GET | `/api/crawl-jobs/{id}/resources` | Resources found (filter by `category`, `q`, `min_score`) |
| GET | `/api/crawl-jobs/{id}/categories` | Category counts |
| GET | `/api/crawl-jobs/{id}/graph` | Knowledge graph edges |
| GET | `/api/search?q=...` | Search across all completed jobs |

## Scaling beyond local/demo use

This implementation favors a working single-process pipeline you can run
immediately. The original architecture (Celery + Redis + Postgres +
Meilisearch + Playwright/Crawl4AI) is the production path:

- **SQLite -> Postgres**: change `DATABASE_URL`; models are already portable
  (the one Postgres-specific JSON query was avoided on purpose).
- **In-process queue -> Redis + Celery**: `_fetch_and_classify` / `_apply_result`
  in `crawler.py` map directly to a Celery task per URL, with the frontier
  as a Redis set/list instead of an in-memory `deque`.
- **httpx fetcher -> Crawl4AI/Playwright**: swap `fetcher.fetch_page` for a
  headless-browser fetcher with the same `FetchResult` signature (see
  comment at the bottom of `fetcher.py`) to handle JS-rendered sites.
- **Heuristic classifier -> LLM-first**: `classifier.py` already supports
  this via `ANTHROPIC_API_KEY`; lower the confidence threshold to send more
  pages through the LLM.
- **Token-overlap dedup -> embeddings**: `dedup.py`'s `_text_similarity` is
  a drop-in replacement target for cosine similarity over embeddings stored
  in pgvector.
