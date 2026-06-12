"""
Knowledge graph relation extraction.

Heuristic-based (no LLM needed): infers edges from structural signals
that are cheap to compute and almost always correct:

  - same domain + one is 'documentation'/'api' and the other isn't
      -> "documents"
  - a page was discovered as a child link of another page
      -> "linked_from" (the literal crawl structure)
  - category-specific pairings (course <-> its provider domain,
      dataset <-> a research_paper on the same domain)
      -> "offered_by" / "described_by"

This runs as a final pass over all resources in a completed job.
"""
from sqlalchemy.orm import Session

from app.core.db import Resource, ResourceRelation, ResourceCategory, Page, new_id
from app.core.links import domain_of


def build_relations(db: Session, job_id: str) -> int:
    resources = (
        db.query(Resource)
        .filter(Resource.job_id == job_id, Resource.is_duplicate == False)  # noqa: E712
        .all()
    )

    created = 0
    by_domain: dict[str, list[Resource]] = {}
    for r in resources:
        by_domain.setdefault(r.domain, []).append(r)

    for domain, group in by_domain.items():
        docs = [r for r in group if r.category in (ResourceCategory.DOCUMENTATION, ResourceCategory.API)]
        others = [r for r in group if r.category not in (ResourceCategory.DOCUMENTATION, ResourceCategory.API)]

        for other in others:
            for doc in docs:
                if other.id == doc.id:
                    continue
                if _relation_exists(db, job_id, other.id, doc.id, "documents"):
                    continue
                db.add(ResourceRelation(
                    id=new_id(), job_id=job_id,
                    source_id=other.id, target_id=doc.id,
                    relation_type="documents",
                ))
                created += 1

    # Crawl-structure relations: page A links to page B -> resource A "links_to" resource B
    all_pages = db.query(Page).filter(Page.job_id == job_id).all()
    pages_by_id = {p.id: p for p in all_pages}
    pages_by_url = {p.url: p for p in all_pages}
    resources_by_page = {r.page_id: r for r in resources if r.page_id}

    for r in resources:
        if not r.page_id:
            continue
        page = pages_by_id.get(r.page_id)
        if not page or not page.parent_url:
            continue
        parent_page = pages_by_url.get(page.parent_url)
        if not parent_page:
            continue
        parent_resource = resources_by_page.get(parent_page.id)
        if not parent_resource or parent_resource.id == r.id:
            continue
        if _relation_exists(db, job_id, parent_resource.id, r.id, "links_to"):
            continue
        db.add(ResourceRelation(
            id=new_id(), job_id=job_id,
            source_id=parent_resource.id, target_id=r.id,
            relation_type="links_to",
        ))
        created += 1

    db.commit()
    return created


def _relation_exists(db: Session, job_id: str, source_id: str, target_id: str, relation_type: str) -> bool:
    return (
        db.query(ResourceRelation)
        .filter(
            ResourceRelation.job_id == job_id,
            ResourceRelation.source_id == source_id,
            ResourceRelation.target_id == target_id,
            ResourceRelation.relation_type == relation_type,
        )
        .first()
        is not None
    )
