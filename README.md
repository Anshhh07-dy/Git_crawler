# Git_crawler
mFastAPI app that recursively crawls a URL (GitHub API for repos, httpx+BeautifulSoup for sites), classifies pages into 16 resource categories via keyword heuristics (+ optional LLM), scores them by authority/freshness/popularity, dedupes, and builds simple knowledge-graph links. SQLite + React frontend, runs locally/Docker not serverless-friendly.
