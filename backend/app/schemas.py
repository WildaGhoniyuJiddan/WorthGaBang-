from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    mode: Literal["pc", "laptop"]
    query: str = Field(min_length=2, max_length=255)
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
    """Rincian 1 komponen dalam bundle: harga input vs referensi retail."""

    query: str
    component_type: str
    price_input: Optional[int] = None
    reference_price: int


class BundleResponse(BaseModel):
    bundle_price: int
    reference_total: int
    score: float
    verdict: str
    recommendation: str
    savings_percent: float
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
