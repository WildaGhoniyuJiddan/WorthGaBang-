from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RawListing(Base):
    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint("listing_hash", name="uq_raw_listings_hash"),
        Index("ix_raw_listings_source_category", "source", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    raw_title: Mapped[str] = mapped_column(Text)
    raw_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_spec_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Deskripsi produk. Wajib diisi kalau sumbernya menyediakan deskripsi —
    # dipakai untuk mendeteksi kondisi asli ("like new", "ex mining").
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    listing_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    listing_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    condition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Nama toko/penjual. Dipakai untuk menilai toko Tokopedia masih aktif.
    seller: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # True kalau Tokopedia menandai toko sebagai Official Store / distributor.
    # Ini sinyal utama pemisah "tokopedia_baru" vs "tokopedia_bekas".
    is_official_store: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Jumlah unit terjual — dipakai untuk deteksi toko tidak aktif.
    sold_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(nullable=True)
    # Nilai kondisi mentah dari Tokopedia ("Bekas"/"Baru"), sumber paling
    # tepercaya karena diisi langsung oleh penjual di halaman produk.
    condition_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    laptop_unit: Mapped[Optional["LaptopUnit"]] = relationship(back_populates="raw_listing", uselist=False)


class PCComponent(Base):
    __tablename__ = "pc_components"
    __table_args__ = (
        UniqueConstraint("component_type", "brand", "model", name="uq_pc_component_identity"),
        Index("ix_pc_components_lookup", "component_type", "brand", "model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component_type: Mapped[str] = mapped_column(String(32), index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(255))
    benchmark_score: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[int] = mapped_column(Integer, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LaptopUnit(Base):
    __tablename__ = "laptop_units"
    __table_args__ = (
        Index("ix_laptop_units_specs", "brand", "cpu", "gpu", "ram_gb", "storage_gb"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_listing_id: Mapped[int] = mapped_column(ForeignKey("raw_listings.id"), index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cpu: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    gpu: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ram_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    screen_size: Mapped[Optional[float]] = mapped_column(nullable=True)
    price: Mapped[int] = mapped_column(Integer)
    condition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    listing_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    raw_listing: Mapped[RawListing] = relationship(back_populates="laptop_unit")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    __table_args__ = (Index("ix_scrape_runs_source_started", "source", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    schedule: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    input_query: Mapped[str] = mapped_column(Text)
    result_score: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # --- Mobile app attribution (nullable; existing rows/web flow unaffected) ---
    # Plain indexed column (no FK): SQLite can't ALTER constraints in migrations.
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    input_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    verdict: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class User(Base):
    """Mobile app user (B1 auth). Passwords are bcrypt-hashed server-side only."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    """Server-side refresh token registry for revocation (B1 logout)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (Index("ix_wishlist_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16), default="pc")
    target_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (Index("ix_alerts_user_active", "user_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16), default="pc")
    component_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_price: Mapped[int] = mapped_column(Integer)
    condition: Mapped[str] = mapped_column(String(16), default="any")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Store(Base):
    """Computer store for LBS demo (B4). prices_json: {"product query": price_idr}."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(64), default="Jakarta", index=True)
    lat: Mapped[float] = mapped_column()
    lng: Mapped[float] = mapped_column()
    prices_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Feedback(Base):
    """PAM course feedback: saran & kesan (B9)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    kesan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    saran: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
