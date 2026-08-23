from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine, get_db
from .models import AnalysisLog, LaptopUnit, PCComponent
from .schemas import AnalyzeRequest, AnalyzeResponse, FreshnessResponse, IngestRequest, LaptopResponse, PCComponentResponse
from .services.ingestion import ListingInput, ingest_listings
from .services.analysis import all_freshness, analyze
from .services.coverage import report_pc_coverage


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "service": "hargapas-api", "environment": settings.environment}


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze_price(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    result, comparisons, freshness = analyze(db, payload)
    db.add(AnalysisLog(mode=payload.mode, input_query=payload.query, result_score=result.score))
    db.commit()
    return AnalyzeResponse(
        mode=payload.mode,
        query=payload.query,
        input_price=payload.price,
        score=result.score,
        verdict=result.verdict,
        recommendation=result.recommendation,
        reference_price=result.reference_price,
        price_delta_percent=result.delta_percent,
        comparisons=comparisons,
        freshness=freshness,
    )


@app.get("/api/v1/catalog/pc", response_model=list[PCComponentResponse])
def pc_catalog(
    component_type: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[PCComponent]:
    statement = select(PCComponent).order_by(desc(PCComponent.updated_at)).limit(limit)
    if component_type:
        statement = statement.where(PCComponent.component_type == component_type)
    if query:
        statement = statement.where(PCComponent.model.ilike(f"%{query}%"))
    return list(db.scalars(statement).all())


@app.get("/api/v1/catalog/laptops", response_model=list[LaptopResponse])
def laptop_catalog(
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[LaptopUnit]:
    statement = select(LaptopUnit).order_by(desc(LaptopUnit.scraped_at)).limit(limit)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            LaptopUnit.model.ilike(pattern)
            | LaptopUnit.cpu.ilike(pattern)
            | LaptopUnit.gpu.ilike(pattern)
            | LaptopUnit.brand.ilike(pattern)
        )
    return list(db.scalars(statement).all())


@app.get("/api/v1/freshness", response_model=FreshnessResponse)
def freshness(db: Session = Depends(get_db)) -> FreshnessResponse:
    return FreshnessResponse(sources=all_freshness(db))


@app.get("/api/v1/catalog/coverage")
def catalog_coverage(
    minimum: int = Query(default=3, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    return report_pc_coverage(db, minimum)


@app.post("/api/v1/ingest/{source}")
def ingest_source(
    source: str,
    payload: IngestRequest,
    x_job_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if source not in {"tokopedia", "shopee", "facebook"}:
        raise HTTPException(status_code=400, detail="Unsupported source")
    if settings.internal_job_token and x_job_token != settings.internal_job_token:
        raise HTTPException(status_code=401, detail="Invalid job token")
    inserted = ingest_listings(
        db,
        source,
        [
            ListingInput(
                title=item.title,
                price=item.price,
                url=item.url,
                spec_text=item.spec_text,
                category=item.category,
                condition=item.condition,
                scraped_at=payload.scraped_at,
            )
            for item in payload.items
        ],
    )
    return {"source": source, "received": len(payload.items), "inserted": inserted}


@app.post("/api/v1/jobs/scrape")
def trigger_scrape(
    query: str | None = Query(default=None, min_length=2),
    x_job_token: str | None = Header(default=None),
) -> dict:
    if settings.internal_job_token and x_job_token != settings.internal_job_token:
        raise HTTPException(status_code=401, detail="Invalid job token")
    from .jobs import run_cycle

    result = run_cycle(query)
    return {
        "query": result["query"],
        "fallback_source": result["fallback_source"],
        "runs": [
            {
                "source": run.source,
                "status": run.status,
                "item_count": run.item_count,
                "error_message": run.error_message,
                "is_fallback": run.is_fallback,
            }
            for run in result["runs"]
        ],
    }
