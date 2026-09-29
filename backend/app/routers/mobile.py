"""WorthBang mobile API router (B1..B9) — /api/v1/*.

Additive only: existing endpoints in main.py are untouched.
"""
from __future__ import annotations

import base64
import hmac
import json
import math
import re
import time
from datetime import timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..auth import (
    decode_token,
    get_current_user,
    hash_password,
    issue_token_pair,
    refresh_is_active,
    revoke_all_user_tokens,
    revoke_refresh_token,
    sign_payload,
    verify_password,
)
from ..config import get_settings
from ..db import get_db
from ..models import (
    AnalysisLog,
    Feedback,
    PCComponent,
    PriceAlert,
    RawListing,
    Store,
    User,
    WishlistItem,
    utcnow,
)
from ..schemas import (
    AlertCreate,
    AlertList,
    AlertResponse,
    BuilderRequest,
    BuilderResponse,
    BuildPart,
    ChatBuild,
    ChatBuildItem,
    ChatRequest,
    ChatResponse,
    CurrencyRatesResponse,
    FeedbackCreate,
    GameQuestionResponse,
    GameSubmitRequest,
    GameSubmitResponse,
    HistoryCreate,
    HistoryItem,
    HistoryList,
    LoginRequest,
    LoginResponse,
    ProfileUpdateResponse,
    RefreshRequest,
    RegisterRequest,
    StoreList,
    StoreResponse,
    TokenResponse,
    TrendPoint,
    TrendResponse,
    UserResponse,
    WishlistCreate,
    WishlistItemResponse,
    WishlistList,
)
from ..services.analysis import new_price_anchor

router = APIRouter(prefix="/api/v1", tags=["mobile"])

_PHOTOS_DIR = Path(__file__).resolve().parents[1] / "data" / "profile_photos"
_MAX_PHOTO_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# B1 — Auth
# ---------------------------------------------------------------------------

def _public_user(user: User) -> UserResponse:
    return UserResponse(id=user.id, name=user.name, email=user.email, photo_url=user.photo_url)


@router.post("/auth/register", response_model=LoginResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Invalid email format")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    access, refresh = issue_token_pair(db, user)
    return LoginResponse(access_token=access, refresh_token=refresh, user=_public_user(user))


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    # Generic message: never reveal which field was wrong.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access, refresh = issue_token_pair(db, user)
    return LoginResponse(access_token=access, refresh_token=refresh, user=_public_user(user))


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user_id = decode_token(payload.refresh_token, "refresh")
    if not refresh_is_active(db, payload.refresh_token):
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Rotate: revoke the old refresh token, issue a fresh pair.
    revoke_refresh_token(db, payload.refresh_token)
    access, refresh = issue_token_pair(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/auth/logout", status_code=204)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    revoke_all_user_tokens(db, user.id)
    return None


# ---------------------------------------------------------------------------
# B2 — History & Wishlist
# ---------------------------------------------------------------------------

@router.get("/history", response_model=HistoryList)
def history(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(AnalysisLog)
        .where(AnalysisLog.user_id == user.id)
        .order_by(desc(AnalysisLog.created_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            HistoryItem(
                id=r.id,
                mode=r.mode,
                query=r.input_query,
                input_price=r.input_price,
                score=r.result_score,
                verdict=r.verdict,
                created_at=r.created_at,
            )
            for r in rows
        ]
    }


@router.post("/history", response_model=HistoryItem, status_code=201)
def history_push(
    payload: HistoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryItem:
    """B10: app backs up a history entry (hash-chain / offline sync).

    Additive only — the auto-attribution in POST /analyze is untouched.
    """
    log = AnalysisLog(
        mode=payload.mode,
        input_query=payload.query.strip(),
        result_score=payload.score,
        user_id=user.id,
        input_price=payload.input_price,
        verdict=payload.verdict.strip(),
    )
    if payload.created_at is not None:
        # Clamp: never store a future timestamp from the client clock.
        now = utcnow()
        log.created_at = min(payload.created_at, now)
    db.add(log)
    db.commit()
    db.refresh(log)
    return HistoryItem(
        id=log.id,
        mode=log.mode,
        query=log.input_query,
        input_price=log.input_price,
        score=log.result_score,
        verdict=log.verdict,
        created_at=log.created_at,
    )


@router.get("/wishlist", response_model=WishlistList)
def wishlist_list(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(WishlistItem)
        .where(WishlistItem.user_id == user.id)
        .order_by(desc(WishlistItem.created_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": [WishlistItemResponse.model_validate(r) for r in rows]}


@router.post("/wishlist", response_model=WishlistItemResponse, status_code=201)
def wishlist_add(
    payload: WishlistCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistItem:
    item = WishlistItem(
        user_id=user.id, query=payload.query.strip(), mode=payload.mode,
        target_price=payload.target_price,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/wishlist/{item_id}", status_code=204)
def wishlist_delete(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = db.get(WishlistItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    db.delete(item)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# B3 — Alerts
# ---------------------------------------------------------------------------

_CTYPES_FOR_REFERENCE = ("gpu", "cpu", "ram", "storage", "motherboard")


def current_reference_price(query: str, component_type: str | None = None) -> int | None:
    """Lightweight market reference for alerts (B3). None if unknown."""
    ctypes = [component_type] if component_type else list(_CTYPES_FOR_REFERENCE)
    for ctype in ctypes:
        try:
            price = new_price_anchor(query, ctype)
        except Exception:
            price = None
        if price:
            return int(price)
    return None


@router.post("/alerts", response_model=AlertResponse, status_code=201)
def alert_create(
    payload: AlertCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    alert = PriceAlert(
        user_id=user.id,
        query=payload.query.strip(),
        mode=payload.mode,
        component_type=payload.component_type,
        target_price=payload.target_price,
        condition=payload.condition,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _alert_dict(alert)


def _alert_dict(alert: PriceAlert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        query=alert.query,
        mode=alert.mode,
        target_price=alert.target_price,
        current_price=current_reference_price(alert.query, alert.component_type),
        is_active=alert.is_active,
        created_at=alert.created_at,
    )


@router.get("/alerts", response_model=AlertList)
def alert_list(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(PriceAlert)
        .where(PriceAlert.user_id == user.id)
        .order_by(desc(PriceAlert.created_at))
    ).all()
    return {"items": [_alert_dict(r) for r in rows]}


@router.delete("/alerts/{alert_id}", status_code=204)
def alert_delete(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    alert = db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# B4 — Stores (LBS)
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/stores/nearby", response_model=StoreList)
def stores_nearby(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, ge=0.5, le=100),
    db: Session = Depends(get_db),
) -> dict:
    stores = db.scalars(select(Store)).all()
    out = []
    for s in stores:
        dist = _haversine_km(lat, lng, s.lat, s.lng)
        if dist <= radius_km:
            try:
                prices = json.loads(s.prices_json) if s.prices_json else {}
            except (json.JSONDecodeError, TypeError):
                prices = {}
            out.append(
                StoreResponse(
                    id=s.id,
                    name=s.name,
                    address=s.address,
                    lat=s.lat,
                    lng=s.lng,
                    distance_km=round(dist, 1),
                    prices={k: int(v) for k, v in prices.items() if isinstance(v, (int, float))},
                )
            )
    out.sort(key=lambda x: x.distance_km)
    return {"stores": out}


# ---------------------------------------------------------------------------
# B5 — Trend (descriptive only, no prediction)
# ---------------------------------------------------------------------------

@router.get("/trend", response_model=TrendResponse)
def trend(
    query: str = Query(min_length=2, max_length=255),
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
) -> TrendResponse:
    since = utcnow() - timedelta(days=days)
    pattern = f"%{query.strip()}%"
    day_col = func.date(RawListing.scraped_at).label("day")
    rows = db.execute(
        select(day_col, func.avg(RawListing.raw_price), func.count(RawListing.id))
        .where(
            RawListing.raw_title.ilike(pattern),
            RawListing.raw_price.is_not(None),
            RawListing.raw_price > 0,
            RawListing.scraped_at >= since,
        )
        .group_by(day_col)
        .order_by(day_col)
    ).all()
    points = [TrendPoint(date=str(day), price=int(avg)) for day, avg, _ in rows if day]
    if len(points) < 2:
        return TrendResponse(
            query=query.strip(), days=days, points=points,
            summary="Belum cukup data historis untuk tren produk ini.",
        )
    prices = [p.price for p in points]
    first, last = prices[0], prices[-1]
    change = round((last - first) / first * 100, 1) if first else 0.0
    avg = int(sum(prices) / len(prices))
    direction = "Down" if change < 0 else "Up" if change > 0 else "Flat"
    vs_avg = (
        "current price is below the period average"
        if last < avg else "current price is above the period average"
        if last > avg else "current price equals the period average"
    )
    summary = (
        f"{direction} {abs(change)}% in the last {days} days — {vs_avg}."
    )
    return TrendResponse(
        query=query.strip(), days=days, points=points,
        min=min(prices), max=max(prices), avg=avg,
        change_percent=change, summary=summary,
    )


# ---------------------------------------------------------------------------
# B6 — Random builder (from retail catalog; PSU prices are estimates)
# ---------------------------------------------------------------------------

_CATALOG: dict | None = None


def _catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        path = Path(__file__).resolve().parents[1] / "data" / "retail_catalog.json"
        try:
            _CATALOG = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _CATALOG = {}
    return _CATALOG


_PSU_ESTIMATES = [
    {"model": "PSU 550W 80+ Bronze (estimasi)", "price": 750000},
    {"model": "PSU 650W 80+ Bronze (estimasi)", "price": 950000},
    {"model": "PSU 750W 80+ Gold (estimasi)", "price": 1350000},
]

_ALLOCATIONS = {
    "gaming": {"gpu": 0.40, "cpu": 0.25, "ram": 0.12, "storage": 0.10, "motherboard": 0.08, "psu": 0.05},
    "office": {"cpu": 0.28, "gpu": 0.10, "ram": 0.15, "storage": 0.12, "motherboard": 0.10, "psu": 0.08},
    "editing": {"cpu": 0.28, "gpu": 0.25, "ram": 0.15, "storage": 0.12, "motherboard": 0.10, "psu": 0.10},
}


def _pick_part(items: list[dict], budget_share: int) -> dict:
    cands = [it for it in items if isinstance(it.get("price"), int) and it["price"] > 0]
    if not cands:
        return {"model": "Tidak tersedia", "price": 0}
    affordable = [it for it in cands if it["price"] <= budget_share]
    pool = affordable or cands
    # Best value proxy within budget: highest-priced affordable item.
    best = max(pool, key=lambda it: it["price"])
    return {"model": best.get("model") or "Unknown", "price": int(best["price"])}


@router.post("/builder/random", response_model=BuilderResponse)
def builder_random(payload: BuilderRequest) -> BuilderResponse:
    use_case = payload.use_case.lower()
    alloc = _ALLOCATIONS.get(use_case, _ALLOCATIONS["gaming"])
    cat = _catalog()
    parts: dict[str, dict] = {}
    for key in ("cpu", "gpu", "ram", "storage", "motherboard"):
        items = cat.get(key) or []
        parts[key] = _pick_part(items if isinstance(items, list) else [], int(payload.budget * alloc[key]))
    psu_budget = int(payload.budget * alloc["psu"])
    psu_cands = [p for p in _PSU_ESTIMATES if p["price"] <= psu_budget] or _PSU_ESTIMATES
    psu = min(psu_cands, key=lambda p: abs(p["price"] - psu_budget))

    def part(d: dict) -> BuildPart:
        return BuildPart(name=d["model"], price=d["price"])

    total = parts["cpu"]["price"] + parts["gpu"]["price"] + parts["ram"]["price"] + parts["storage"]["price"] + psu["price"]
    # motherboard excluded from total (case-dependent); keep contract shape
    return BuilderResponse(
        cpu=part(parts["cpu"]), gpu=part(parts["gpu"]), ram=part(parts["ram"]),
        ssd=part(parts["storage"]), psu=BuildPart(name=psu["model"], price=psu["price"]),
        total=total, budget=payload.budget,
    )


# ---------------------------------------------------------------------------
# B7 — Chatbot (Gemini server-side; app never holds the key)
# ---------------------------------------------------------------------------

_BUDGET_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(juta|jt|miliar|m|rb|ribu|k)?", re.IGNORECASE)


def _extract_budget_idr(message: str) -> int | None:
    m = _BUDGET_RE.search(message.replace(",", "."))
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult = {"juta": 1_000_000, "jt": 1_000_000, "miliar": 1_000_000_000, "m": 1_000_000,
            "rb": 1_000, "ribu": 1_000, "k": 1_000}.get(unit, 1)
    # Bare numbers like 8000000 are already IDR; "8" alone is ambiguous -> ignore.
    if mult == 1 and num < 1000:
        return None
    return int(num * mult)


def _catalog_context(message: str, budget: int | None, limit: int = 14) -> str:
    tokens = {t for t in re.findall(r"[a-z0-9]+", message.lower()) if len(t) > 2}
    cat = _catalog()
    scored: list[tuple[int, str, int]] = []
    for key in ("gpu", "cpu", "ram", "storage", "motherboard"):
        items = cat.get(key) or []
        if not isinstance(items, list):
            continue
        for it in items:
            model = str(it.get("model") or "")
            price = it.get("price")
            if not model or not isinstance(price, int) or price <= 0:
                continue
            mtok = set(re.findall(r"[a-z0-9]+", model.lower()))
            overlap = len(tokens & mtok)
            if overlap or (budget and price <= budget):
                scored.append((overlap, f"[{key}] {model}", price))
    scored.sort(key=lambda x: (-x[0], x[2]))
    lines = [f"- {name}: Rp{price:,}".replace(",", ".") for _, name, price in scored[:limit]]
    return "\n".join(lines) if lines else "(katalog kosong)"


async def _gemini_text(prompt: str) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Chat service not configured")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
    except Exception:
        raise HTTPException(status_code=503, detail="Chat service unavailable, try again later")
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail="Chat service unavailable, try again later")
    try:
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(status_code=503, detail="Chat service returned an unexpected response")


@router.post("/chat/ask", response_model=ChatResponse)
async def chat_ask(payload: ChatRequest) -> ChatResponse:
    budget = _extract_budget_idr(payload.message)
    context = _catalog_context(payload.message, budget)
    history_lines = "\n".join(
        f"{m.role}: {m.text}" for m in payload.history[-10:]
    )
    prompt = (
        "Kamu 'Bang Worth', asisten rakit PC berbahasa Indonesia yang santai.\n"
        "Susun rekomendasi rakitan dari DAFTAR HARGA berikut (harga IDR, data real). "
        "JANGAN mengarang harga di luar daftar.\n"
        f"Budget user (terdeteksi): {budget if budget else 'tidak disebut'}\n"
        f"Riwayat chat:\n{history_lines or '(kosong)'}\n"
        f"DAFTAR HARGA:\n{context}\n"
        "Balas HANYA dengan JSON valid (tanpa markdown fence): "
        '{"reply": "<teks santai Bahasa Indonesia>", '
        '"build": {"items": [{"component": "CPU|GPU|RAM|SSD|Motherboard", "name": "<nama dari daftar>", "price": <int>}], '
        '"total": <int>, "note": "<catatan singkat>"}}'
    )
    text = await _gemini_text(prompt)
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return ChatResponse(reply=text[:2000])
    build = None
    if isinstance(data.get("build"), dict):
        b = data["build"]
        try:
            build = ChatBuild(
                items=[ChatBuildItem(component=str(i.get("component", ""))[:32],
                                     name=str(i.get("name", ""))[:255],
                                     price=int(i.get("price", 0)))
                       for i in b.get("items", [])[:10]],
                total=int(b.get("total", 0)),
                note=str(b.get("note", ""))[:500],
            )
        except (TypeError, ValueError):
            build = None
    return ChatResponse(reply=str(data.get("reply", ""))[:2000], build=build)


# ---------------------------------------------------------------------------
# B8 — Game "Tebak Harga" (stateless signed question ids)
# ---------------------------------------------------------------------------

def _game_token(product_ref: str, price: int) -> str:
    payload = json.dumps(
        {"p": product_ref, "a": price, "e": int(time.time()) + 3600}
    ).encode()
    sig = sign_payload(payload)
    return base64.urlsafe_b64encode(payload).decode() + "." + sig


def _game_verify(token: str) -> tuple[str, int]:
    try:
        b64, sig = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode())
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail="Invalid question id")
    if not hmac.compare_digest(sig, sign_payload(payload)):
        raise HTTPException(status_code=400, detail="Invalid question id")
    try:
        data = json.loads(payload.decode())
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid question id")
    if data.get("e", 0) < int(time.time()):
        raise HTTPException(status_code=400, detail="Question expired, get a new one")
    return str(data["p"]), int(data["a"])


@router.get("/game/question", response_model=GameQuestionResponse)
def game_question(db: Session = Depends(get_db)) -> GameQuestionResponse:
    row = db.scalar(
        select(PCComponent)
        .where(PCComponent.avg_price > 0, PCComponent.sample_count >= 3)
        .order_by(func.random())
        .limit(1)
    )
    if row is not None:
        product = f"{(row.brand or '').strip()} {row.model}".strip()
        specs = (
            f"Komponen PC: {row.component_type.upper()} • "
            f"Benchmark score: {row.benchmark_score} • "
            f"Berdasarkan {row.sample_count} listing pasar"
        )
        hint = "Kisaran harga: beberapa juta rupiah"
        return GameQuestionResponse(
            question_id=_game_token(f"pc:{row.id}", row.avg_price),
            product=product or row.model, specs=specs, hint=hint,
        )
    # Fallback: retail catalog (no DB rows yet)
    cat = _catalog()
    items = [it for key in ("gpu", "cpu") for it in (cat.get(key) or []) if isinstance(it.get("price"), int)]
    if not items:
        raise HTTPException(status_code=503, detail="No game data available yet")
    import random as _random

    it = _random.choice(items)
    return GameQuestionResponse(
        question_id=_game_token(f"cat:{it['model'][:40]}", it["price"]),
        product=str(it["model"])[:120],
        specs="Komponen PC dari katalog retail Indonesia",
        hint="Kisaran harga: beberapa juta rupiah",
    )


@router.post("/game/submit", response_model=GameSubmitResponse)
def game_submit(payload: GameSubmitRequest) -> GameSubmitResponse:
    _, actual = _game_verify(payload.question_id)
    diff = payload.guess_idr - actual
    score = round(max(0.0, 100 - abs(diff) / actual * 100)) if actual > 0 else 0
    return GameSubmitResponse(actual_price=actual, difference=diff, score=score)


# ---------------------------------------------------------------------------
# B9 — Currency, Feedback, Profile
# ---------------------------------------------------------------------------

_fx_cache: dict = {"rates": None, "updated_at": None}

_FX_FALLBACK = {"USD": 0.000062, "SGD": 0.000083, "MYR": 0.00029}  # per 1 IDR, approx


@router.get("/currency/rates", response_model=CurrencyRatesResponse)
def currency_rates(base: str = Query(default="IDR", max_length=8)) -> CurrencyRatesResponse:
    base = base.upper()
    now = utcnow()
    cached_at = _fx_cache["updated_at"]
    stale = cached_at is None or (now - cached_at).total_seconds() > 3600
    if stale:
        try:
            resp = httpx.get(get_settings().fx_api_url, timeout=8)
            data = resp.json()
            rates = {k: float(data["rates"][k]) for k in ("USD", "SGD", "MYR") if k in data.get("rates", {})}
            if rates:
                _fx_cache["rates"] = rates
                _fx_cache["updated_at"] = now
        except Exception:
            # Network/proxy/DNS failure -> fall back to bundled approximate rates.
            pass
    rates = _fx_cache["rates"] or dict(_FX_FALLBACK)
    if _fx_cache["updated_at"] is None:
        _fx_cache["updated_at"] = now
    if base != "IDR":
        if base not in rates or not rates[base]:
            raise HTTPException(status_code=400, detail=f"Unsupported base currency: {base}")
        pivot = rates[base]
        rates = {k: (1.0 if k == base else v / pivot) for k, v in rates.items()}
        rates["IDR"] = 1 / pivot
    return CurrencyRatesResponse(base=base, rates=rates, updated_at=_fx_cache["updated_at"])


@router.post("/feedback", status_code=201)
def feedback_create(
    payload: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not (payload.kesan or "").strip() and not (payload.saran or "").strip():
        raise HTTPException(status_code=422, detail="Please write your impressions and suggestions")
    fb = Feedback(
        user_id=user.id, rating=payload.rating,
        kesan=(payload.kesan or "").strip() or None,
        saran=(payload.saran or "").strip() or None,
    )
    db.add(fb)
    db.commit()
    return {"id": fb.id}


@router.put("/users/me", response_model=ProfileUpdateResponse)
async def profile_update(
    name: str | None = Form(default=None),
    photo: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        if len(name) > 128:
            raise HTTPException(status_code=422, detail="Name too long")
        user.name = name
    if photo is not None:
        ctype = (photo.content_type or "").lower()
        if not ctype.startswith("image/"):
            raise HTTPException(status_code=422, detail="Photo must be an image file")
        _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ctype, ".jpg")
        data = await photo.read()
        if len(data) > _MAX_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail="Photo too large (max 5MB)")
        if not data:
            raise HTTPException(status_code=422, detail="Empty photo file")
        filename = f"user_{user.id}{ext}"
        (_PHOTOS_DIR / filename).write_bytes(data)
        user.photo_url = f"/api/v1/files/profile_photos/{filename}"
    db.commit()
    db.refresh(user)
    return user


@router.get("/files/profile_photos/{filename}")
def profile_photo(filename: str) -> FileResponse:
    if not re.fullmatch(r"user_\d+\.(jpg|png|webp)", filename):
        raise HTTPException(status_code=404, detail="Photo not found")
    path = _PHOTOS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path)
