from contextlib import asynccontextmanager
import logging
import traceback

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine, get_db
from .security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    require_job_token,
)
from .models import AnalysisLog, LaptopUnit, PCComponent
from .schemas import (
    Alternative,
    AnalyzeRequest,
    AnalyzeResponse,
    BundleItemBreakdown,
    BundleRequest,
    BundleResponse,
    FreshnessResponse,
    IngestRequest,
    LaptopResponse,
    PCComponentResponse,
)
from .services.ingestion import ListingInput, ingest_listings
from .services.analysis import all_freshness, analyze, new_price_anchor, resolve_bundle_item_prices
from .services.scoring import score_price
from .services.coverage import report_pc_coverage
from .services.suggest import suggest_components


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _log_exception(request: Request, exc: Exception):
    logging.error("UNHANDLED %s %s: %s\n%s", request.method, request.url.path, exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "service": "worthgabang-api", "environment": settings.environment}


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze_price(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    result, comparisons, freshness, alternatives = analyze(db, payload)
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
        fair_price_low=result.fair_price_low,
        fair_price_high=result.fair_price_high,
        tier_label=result.tier_label,
        new_reference_price=result.new_reference_price,
        used_reference_price=result.used_reference_price,
        cross_market_advice=result.cross_market_advice,
        comparisons=comparisons,
        alternatives=[Alternative(**alt) for alt in alternatives],
        freshness=freshness,
    )


@app.post("/api/v1/analyze-bundle", response_model=BundleResponse)
def analyze_bundle(payload: BundleRequest, db: Session = Depends(get_db)) -> BundleResponse:
    """Worth-it cek paket bundling (mis. Mobo + CPU / CPU + GPU).

    Referensi dihitung per item untuk harga BARU dan BEKAS dari dataset database & retail.
    Total bundle dibandingkan terhadap penjumlahan harga pasar baru dan bekas.
    """
    breakdown: list[BundleItemBreakdown] = []
    new_total = 0
    used_total = 0
    missing: list[str] = []

    for item in payload.items:
        ctype = item.component_type or "cpu"
        ref_primary, new_ref, used_ref = resolve_bundle_item_prices(db, item.query, ctype)

        if ref_primary <= 0:
            missing.append(item.query)

        new_total += (new_ref or ref_primary or 0)
        used_total += (used_ref or (int(ref_primary * 0.70) if ref_primary else 0))

        breakdown.append(
            BundleItemBreakdown(
                query=item.query,
                component_type=ctype,
                price_input=item.price,
                reference_price=ref_primary,
                new_reference_price=new_ref,
                used_reference_price=used_ref,
            )
        )

    if new_total <= 0 and used_total <= 0:
        detail = f"Harga referensi tidak ditemukan untuk: {', '.join(missing)}" if missing else "Referensi tidak tersedia."
        raise HTTPException(status_code=422, detail=detail)

    reference_total = new_total if new_total > 0 else used_total

    # Hitung rasio penghematan terhadap harga BARU dan BEKAS
    savings_percent = round((1 - payload.bundle_price / reference_total) * 100, 1) if reference_total > 0 else 0.0
    savings_used_percent = round((1 - payload.bundle_price / used_total) * 100, 1) if used_total > 0 else None

    # Tentukan skor dan verdict
    result = score_price(payload.bundle_price, [reference_total])

    new_total_str = f"Rp{new_total:,}".replace(",", ".")
    used_total_str = f"Rp{used_total:,}".replace(",", ".")
    bundle_str = f"Rp{payload.bundle_price:,}".replace(",", ".")

    # Buat saran lintas pasar (cross-market advice)
    if savings_percent >= 10:
        rec = f"Paket ini hemat {savings_percent}% dibeli bundling dibanding beli baru terpisah (total normal {new_total_str}). Worth it."
    elif savings_percent >= 0:
        rec = f"Bundling ini hemat {savings_percent}% dibanding beli baru terpisah (total normal {new_total_str}). Masuk akal jika butuh semua komponennya."
    else:
        rec = f"Paket lebih mahal {abs(savings_percent)}% dibanding beli baru terpisah (total normal {new_total_str}). Pertimbangkan beli satuan."

    cross_market_advice = (
        f"🏷️ Total Baru Retail: {new_total_str} (hemat {savings_percent}%) | "
        f"📦 Total Estimasi Bekas: {used_total_str}"
        + (f" (hemat {savings_used_percent}%)" if savings_used_percent is not None else "")
        + f". Tawaran paket seharga {bundle_str} "
        + ("sangat menarik karena di bawah harga total part bekas eceran!" if savings_used_percent and savings_used_percent > 0 else "sesuai rentang pasar.")
    )

    return BundleResponse(
        bundle_price=payload.bundle_price,
        reference_total=reference_total,
        new_reference_total=new_total,
        used_reference_total=used_total,
        score=result.score,
        verdict=result.verdict,
        recommendation=rec,
        savings_percent=savings_percent,
        savings_used_percent=savings_used_percent,
        cross_market_advice=cross_market_advice,
        items=breakdown,
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


@app.get("/api/v1/suggest/{section}")
def suggest(
    section: str,
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=8, ge=1, le=20),
    condition: str = Query(default="any", pattern="^(baru|bekas|any)$"),
    db: Session = Depends(get_db),
) -> dict:
    """Autocomplete per section; condition=baru (katalog retail) | bekas (marketplace)."""
    return {"section": section, "suggestions": suggest_components(db, section, q, limit, condition)}


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
    _: str = Depends(require_job_token),
    db: Session = Depends(get_db),
) -> dict:
    if source not in {"facebook_marketplace", "tokopedia"}:
        raise HTTPException(status_code=400, detail="Unsupported source")
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
    _: str = Depends(require_job_token),
) -> dict:
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


@app.post("/api/v1/jobs/pipeline/{name}")
def trigger_pipeline(
    name: str,
    _: str = Depends(require_job_token),
) -> dict:
    """Trigger pipeline pengumpulan harga BARU: 'pc' atau 'laptop' (blocking)."""
    from .jobs import run_pipeline_laptop, run_pipeline_pc

    if name == "pc":
        return run_pipeline_pc(progress=lambda m: None)
    if name == "laptop":
        return run_pipeline_laptop(progress=lambda m: None)
    raise HTTPException(status_code=404, detail=f"Pipeline tidak dikenal: {name}")


# Debug endpoint for database connection
@app.get("/api/v1/debug/db")
def debug_db(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(select(1))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/debug/env")
def debug_env():
    # Return non-sensitive environment variables for debugging
    safe_vars = ['ENVIRONMENT', 'CORS_ORIGINS', 'NEXT_PUBLIC_API_BASE_URL']
    result = {}
    for var in safe_vars:
        result[var] = os.getenv(var, 'not set')
    # Also check if DATABASE_URL is set (but don't show the value)
    result['DATABASE_URL_SET'] = 'set' if os.getenv('DATABASE_URL') else 'not set'
    return result

@app.get("/test")
def test():
    return {"message": "hello"}

