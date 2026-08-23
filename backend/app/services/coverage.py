from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import RawListing
from ..schemas import AnalyzeRequest
from .analysis import _pc_comparisons
from .relevance import component_type_from_query, is_standalone_component_query


def report_pc_coverage(session: Session, minimum: int = 3) -> dict:
    settings = get_settings()
    items = []
    for query in settings.query_list:
        component_type = component_type_from_query(query)
        if component_type is None or not is_standalone_component_query(query):
            continue
        comparisons = _pc_comparisons(
            session,
            AnalyzeRequest(mode="pc", query=query, price=1, component_type=component_type),
        )
        items.append(
            {
                "query": query,
                "component_type": component_type,
                "comparison_count": len(comparisons),
                "status": "empty" if not comparisons else "low" if len(comparisons) < minimum else "ok",
            }
        )
    source_counts = dict(
        session.execute(
            select(RawListing.source, func.count()).where(RawListing.category == "pc").group_by(RawListing.source)
        ).all()
    )
    return {
        "generated_at": datetime.now(timezone.utc),
        "minimum_comparisons": minimum,
        "source_counts": source_counts,
        "total_queries": len(items),
        "empty_queries": [item["query"] for item in items if item["status"] == "empty"],
        "low_sample_queries": [item["query"] for item in items if item["status"] == "low"],
        "items": items,
    }
