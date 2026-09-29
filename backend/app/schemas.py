from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    mode: Literal["pc", "laptop"]
    # PC: query wajib (model komponen). Laptop: boleh pakai cpu/gpu/ram_gb/
    # storage_gb tanpa query (frontend isi field terpisah).
    query: str = Field(default="", min_length=0, max_length=255)
    price: int = Field(gt=0)
    component_type: Optional[str] = Field(default=None, max_length=32)
    brand: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=255)
    cpu: Optional[str] = Field(default=None, max_length=128)
    gpu: Optional[str] = Field(default=None, max_length=128)
    ram_gb: Optional[int] = Field(default=None, gt=0, le=1024)
    storage_gb: Optional[int] = Field(default=None, gt=0, le=32768)
    screen_size: Optional[float] = Field(default=None, gt=0, le=100)
    condition: Optional[str] = Field(default="any", max_length=32)

    @model_validator(mode="after")
    def _require_input(self) -> "AnalyzeRequest":
        if self.mode == "pc" and len((self.query or "").strip()) < 2:
            raise ValueError("Query komponen wajib diisi untuk mode PC.")
        if self.mode == "laptop" and not (self.query or "").strip() and not (
            self.cpu or self.gpu or self.ram_gb or self.storage_gb
        ):
            raise ValueError("Isi minimal satu spesifikasi laptop (CPU, GPU, RAM, atau storage).")
        return self


class BundleItem(BaseModel):
    """Komponen dalam cek bundle: query model + harga item (opsional kalau bundle)."""

    query: str = Field(min_length=2, max_length=255)
    component_type: Optional[str] = Field(default="cpu", max_length=32)
    price: Optional[int] = Field(default=None, gt=0)


class BundleRequest(BaseModel):
    """Cek worth-it paket bundling multi-komponen (mis. Mobo + CPU)."""

    items: list[BundleItem] = Field(min_length=1, max_length=6)
    bundle_price: int = Field(gt=0)
    condition: Optional[str] = Field(default="any", max_length=32)


class BundleItemBreakdown(BaseModel):
    """Rincian 1 komponen dalam bundle: harga input vs referensi baru & bekas."""

    query: str
    component_type: str
    price_input: Optional[int] = None
    reference_price: int
    new_reference_price: Optional[int] = None
    used_reference_price: Optional[int] = None


class BundleResponse(BaseModel):
    bundle_price: int
    reference_total: int
    new_reference_total: Optional[int] = None
    used_reference_total: Optional[int] = None
    score: float
    verdict: str
    recommendation: str
    savings_percent: float
    savings_used_percent: Optional[float] = None
    cross_market_advice: Optional[str] = None
    items: list[BundleItemBreakdown]


class Comparison(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    price: int
    source: str
    listing_url: Optional[str] = None
    similarity: float = Field(ge=0, le=1)
    condition: Optional[str] = None


class Alternative(BaseModel):
    """Kandidat benchmark lebih baik di harga serupa (PassMark)."""

    name: str
    score: int
    est_price_idr: int
    gain_percent: int
    vram_gb: Optional[int] = None
    tier_label: Optional[str] = None


class Freshness(BaseModel):
    last_updated_at: Optional[datetime] = None
    age_seconds: Optional[int] = None
    label: str
    is_stale: bool
    primary_source: str


class AnalyzeResponse(BaseModel):
    mode: str
    query: str
    input_price: int
    score: float
    verdict: str
    recommendation: str
    reference_price: int
    price_delta_percent: float
    fair_price_low: int = 0
    fair_price_high: int = 0
    tier_label: Optional[str] = None
    new_reference_price: Optional[int] = None
    used_reference_price: Optional[int] = None
    cross_market_advice: Optional[str] = None
    comparisons: list[Comparison]
    alternatives: list[Alternative] = []
    freshness: Freshness


class PCComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    component_type: str
    brand: Optional[str]
    model: str
    benchmark_score: int
    avg_price: int
    sample_count: int
    updated_at: datetime


class LaptopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: Optional[str]
    model: Optional[str]
    cpu: Optional[str]
    gpu: Optional[str]
    ram_gb: Optional[int]
    storage_gb: Optional[int]
    screen_size: Optional[float]
    price: int
    condition: Optional[str]
    source: str
    listing_url: Optional[str]
    scraped_at: datetime


class FreshnessResponse(BaseModel):
    sources: dict[str, Freshness]


class IngestItem(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    price: int | str | None = None
    url: Optional[str] = None
    spec_text: Optional[str] = None
    category: Optional[Literal["pc", "laptop"]] = None
    condition: Optional[str] = None


class IngestRequest(BaseModel):
    items: list[IngestItem] = Field(min_length=1, max_length=500)
    scraped_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Mobile API (WorthBang Android) — B1..B9
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    photo_url: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    user: UserResponse


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mode: str
    query: str
    input_price: Optional[int] = None
    score: float
    verdict: Optional[str] = None
    created_at: datetime


class HistoryCreate(BaseModel):
    """B10: app pushes a history entry (e.g. hash-chain backup / offline sync)."""

    mode: str = Field(pattern="^(pc|laptop)$")
    query: str = Field(min_length=2, max_length=255)
    input_price: int = Field(gt=0)
    score: float = Field(ge=0, le=100)
    verdict: str = Field(min_length=2, max_length=32)
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="after")
    @classmethod
    def _normalize_to_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Mobile clients often omit the offset — assume UTC for naive input.
        Aware input is converted to UTC so storage is always consistent
        (SQLite drops tzinfo on read, which would otherwise keep wall time)."""
        if v is None:
            return v
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class WishlistCreate(BaseModel):
    query: str = Field(min_length=2, max_length=255)
    mode: str = Field(default="pc", max_length=16)
    target_price: Optional[int] = Field(default=None, gt=0)


class WishlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    mode: str
    target_price: Optional[int] = None
    created_at: datetime


class AlertCreate(BaseModel):
    query: str = Field(min_length=2, max_length=255)
    mode: str = Field(default="pc", max_length=16)
    component_type: Optional[str] = Field(default=None, max_length=32)
    target_price: int = Field(gt=0)
    condition: str = Field(default="any", max_length=16)


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    mode: str
    target_price: int
    current_price: Optional[int] = None
    is_active: bool
    created_at: datetime


class StoreResponse(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    lat: float
    lng: float
    distance_km: float
    prices: dict[str, int] = {}


class TrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    price: int


class TrendResponse(BaseModel):
    query: str
    days: int
    points: list[TrendPoint]
    min: Optional[int] = None
    max: Optional[int] = None
    avg: Optional[int] = None
    change_percent: Optional[float] = None
    summary: str


class BuildPart(BaseModel):
    name: str
    price: int


class BuilderRequest(BaseModel):
    budget: int = Field(gt=0)
    use_case: str = Field(default="gaming", max_length=16)


class BuilderResponse(BaseModel):
    cpu: BuildPart
    gpu: BuildPart
    ram: BuildPart
    ssd: BuildPart
    psu: BuildPart
    total: int
    budget: int


class ChatMessage(BaseModel):
    role: str = Field(max_length=16)
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)


class ChatBuildItem(BaseModel):
    component: str
    name: str
    price: int


class ChatBuild(BaseModel):
    items: list[ChatBuildItem]
    total: int
    note: str = ""


class ChatResponse(BaseModel):
    reply: str
    build: Optional[ChatBuild] = None


class GameQuestionResponse(BaseModel):
    question_id: str
    product: str
    specs: str
    hint: str = ""


class GameSubmitRequest(BaseModel):
    question_id: str = Field(min_length=10)
    guess_idr: int = Field(gt=0)


class GameSubmitResponse(BaseModel):
    actual_price: int
    difference: int  # guess - actual (negative = under)
    score: int


class CurrencyRatesResponse(BaseModel):
    base: str
    rates: dict[str, float]
    updated_at: datetime


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    kesan: Optional[str] = Field(default=None, max_length=2000)
    saran: Optional[str] = Field(default=None, max_length=2000)


class ProfileUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    photo_url: Optional[str] = None


class HistoryList(BaseModel):
    items: list[HistoryItem]


class WishlistList(BaseModel):
    items: list[WishlistItemResponse]


class AlertList(BaseModel):
    items: list[AlertResponse]


class StoreList(BaseModel):
    stores: list[StoreResponse]
