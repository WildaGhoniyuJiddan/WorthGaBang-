"""Tests for the WorthBang mobile API (B1..B9) — additive, existing endpoints untouched."""
import io
import os
import tempfile
from datetime import timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test_mobile.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AnalysisLog, PCComponent, RawListing, Store, utcnow


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _register(client, email="dan@x.com", password="min8karakter", name="Dan"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def _auth_headers(client, email="dan@x.com", password="min8karakter"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["refresh_token"]


# ---------------- B1: auth ----------------

def test_register_login_flow(client):
    r = _register(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "dan@x.com"
    assert "password" not in body["user"]

    r = client.post("/api/v1/auth/login", json={"email": "dan@x.com", "password": "min8karakter"})
    assert r.status_code == 200
    assert r.json()["user"]["name"] == "Dan"


def test_register_duplicate_409(client):
    _register(client, email="dup@x.com")
    r = _register(client, email="dup@x.com")
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered"


def test_register_short_password_422(client):
    r = _register(client, email="short@x.com", password="123")
    assert r.status_code == 422


def test_login_wrong_password_generic_401(client):
    _register(client, email="wrongpw@x.com")
    r = client.post("/api/v1/auth/login", json={"email": "wrongpw@x.com", "password": "salahpass"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"
    # unknown email -> same generic message (no user enumeration)
    r = client.post("/api/v1/auth/login", json={"email": "nope@x.com", "password": "salahpass"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


def test_refresh_rotation(client):
    _register(client, email="rot@x.com")
    r = client.post("/api/v1/auth/login", json={"email": "rot@x.com", "password": "min8karakter"})
    refresh1 = r.json()["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r.status_code == 200
    refresh2 = r.json()["refresh_token"]
    assert refresh2 != refresh1
    # old refresh token is revoked after rotation
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r.status_code == 401


def test_refresh_invalid_401(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "bogus.token.here"})
    assert r.status_code == 401


def test_logout_revokes(client):
    _register(client, email="logout@x.com")
    headers, refresh = _auth_headers(client, email="logout@x.com")
    r = client.post("/api/v1/auth/logout", headers=headers)
    assert r.status_code == 204
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


def test_protected_requires_auth(client):
    assert client.get("/api/v1/history").status_code == 401
    assert client.get("/api/v1/wishlist").status_code == 401
    r = client.get("/api/v1/history", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


# ---------------- B2: history & wishlist ----------------

def test_history_attributed_from_analyze(client):
    _register(client, email="hist@x.com")
    headers, _ = _auth_headers(client, email="hist@x.com")
    r = client.post(
        "/api/v1/analyze",
        json={"mode": "pc", "query": "RTX 4060", "price": 4500000, "condition": "any"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/history", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["query"] == "RTX 4060"
    assert items[0]["input_price"] == 4500000
    # other user's history is isolated
    _register(client, email="hist2@x.com")
    headers2, _ = _auth_headers(client, email="hist2@x.com")
    assert client.get("/api/v1/history", headers=headers2).json()["items"] == []


# ---------------- B10: push history (hash-chain backup / offline sync) ----------------

def test_history_push_and_list(client):
    _register(client, email="hpush@x.com")
    headers, _ = _auth_headers(client, email="hpush@x.com")
    r = client.post(
        "/api/v1/history",
        json={"mode": "laptop", "query": "MacBook Air M1", "input_price": 11500000,
              "score": 88.5, "verdict": "worth it"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["query"] == "MacBook Air M1"
    assert item["input_price"] == 11500000
    assert item["score"] == 88.5
    assert item["verdict"] == "worth it"
    # appears in GET /history, newest first
    items = client.get("/api/v1/history", headers=headers).json()["items"]
    assert any(i["id"] == item["id"] for i in items)


def test_history_push_isolated_per_user(client):
    _register(client, email="hpush2@x.com")
    headers, _ = _auth_headers(client, email="hpush2@x.com")
    r = client.post(
        "/api/v1/history",
        json={"mode": "pc", "query": "RTX 4060", "input_price": 4500000,
              "score": 82.0, "verdict": "wajar"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    _register(client, email="hpush3@x.com")
    headers3, _ = _auth_headers(client, email="hpush3@x.com")
    assert client.get("/api/v1/history", headers=headers3).json()["items"] == []


def test_history_push_requires_auth(client):
    r = client.post(
        "/api/v1/history",
        json={"mode": "pc", "query": "RTX 4060", "input_price": 4500000,
              "score": 82.0, "verdict": "wajar"},
    )
    assert r.status_code == 401


def test_history_push_validation(client):
    _register(client, email="hpush4@x.com")
    headers, _ = _auth_headers(client, email="hpush4@x.com")
    # bad mode
    r = client.post("/api/v1/history",
                    json={"mode": "tablet", "query": "iPad", "input_price": 5000000,
                          "score": 80.0, "verdict": "wajar"}, headers=headers)
    assert r.status_code == 422
    # score out of range
    r = client.post("/api/v1/history",
                    json={"mode": "pc", "query": "RTX 4060", "input_price": 4500000,
                          "score": 150.0, "verdict": "wajar"}, headers=headers)
    assert r.status_code == 422


def test_wishlist_crud(client):
    _register(client, email="wish@x.com")
    headers, _ = _auth_headers(client, email="wish@x.com")
    r = client.post("/api/v1/wishlist", json={"query": "RTX 4060", "mode": "pc"}, headers=headers)
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    r = client.get("/api/v1/wishlist", headers=headers)
    assert len(r.json()["items"]) == 1
    r = client.delete(f"/api/v1/wishlist/{item_id}", headers=headers)
    assert r.status_code == 204
    assert client.get("/api/v1/wishlist", headers=headers).json()["items"] == []
    assert client.delete("/api/v1/wishlist/999999", headers=headers).status_code == 404


# ---------------- B3: alerts ----------------

def test_alerts_crud(client):
    _register(client, email="alert@x.com")
    headers, _ = _auth_headers(client, email="alert@x.com")
    r = client.post(
        "/api/v1/alerts",
        json={"query": "RTX 4060", "mode": "pc", "target_price": 4300000, "condition": "any"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["target_price"] == 4300000
    assert body["is_active"] is True
    assert "current_price" in body
    alert_id = body["id"]
    r = client.get("/api/v1/alerts", headers=headers)
    assert len(r.json()["items"]) == 1
    assert client.delete(f"/api/v1/alerts/{alert_id}", headers=headers).status_code == 204
    assert client.get("/api/v1/alerts", headers=headers).json()["items"] == []


# ---------------- B4: stores ----------------

def _seed_store():
    with SessionLocal() as db:
        if db.scalar(select(Store).where(Store.name == "Toko Test")):
            return
        db.add(Store(
            name="Toko Test", address="Jl. Test 1", city="Jakarta",
            lat=-6.2000, lng=106.8000,
            prices_json='{"RTX 4060": 4700000}',
        ))
        db.commit()


def test_stores_nearby(client):
    _seed_store()
    r = client.get("/api/v1/stores/nearby", params={"lat": -6.21, "lng": 106.81, "radius_km": 10})
    assert r.status_code == 200, r.text
    stores = r.json()["stores"]
    names = [s["name"] for s in stores]
    assert "Toko Test" in names
    toko = next(s for s in stores if s["name"] == "Toko Test")
    assert toko["distance_km"] > 0
    assert toko["prices"]["RTX 4060"] == 4700000
    # far away -> empty
    r = client.get("/api/v1/stores/nearby", params={"lat": 0.0, "lng": 100.0, "radius_km": 10})
    assert r.json()["stores"] == []


# ---------------- B5: trend ----------------

def _seed_listings():
    with SessionLocal() as db:
        exists = db.scalar(select(RawListing).where(RawListing.raw_title.like("%TRENDTEST%")))
        if exists:
            return
        now = utcnow()
        for day in range(10):
            for i in range(3):
                db.add(RawListing(
                    source="tokopedia", category="pc",
                    raw_title=f"TRENDTEST GPU Card Batch {day}",
                    raw_price=4_000_000 + day * 50_000,
                    listing_hash=f"trendtest-{day}-{i}",
                    scraped_at=now - timedelta(days=9 - day),
                ))
        db.commit()


def test_trend(client):
    _seed_listings()
    r = client.get("/api/v1/trend", params={"query": "TRENDTEST", "days": 30})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["points"]) >= 5
    assert body["min"] <= body["avg"] <= body["max"]
    assert body["change_percent"] is not None
    assert "days" in body["summary"]
    assert "prediksi" not in body["summary"].lower()


def test_trend_no_data(client):
    r = client.get("/api/v1/trend", params={"query": "ZZZNODATA123", "days": 30})
    assert r.status_code == 200
    assert r.json()["points"] == []


# ---------------- B6: builder ----------------

def test_builder_random(client):
    r = client.post("/api/v1/builder/random", json={"budget": 10000000, "use_case": "gaming"})
    assert r.status_code == 200, r.text
    body = r.json()
    for part in ("cpu", "gpu", "ram", "ssd", "psu"):
        assert body[part]["name"]
        assert body[part]["price"] > 0
    assert body["total"] > 0
    assert body["budget"] == 10000000


# ---------------- B7: chat (no key -> 503) ----------------

def test_chat_no_key_503(client):
    r = client.post("/api/v1/chat/ask", json={"message": "rakit PC 8 juta"})
    assert r.status_code == 503


# ---------------- B8: game ----------------

def _seed_components():
    with SessionLocal() as db:
        exists = db.scalar(select(PCComponent).where(PCComponent.model == "GAMETEST 4060"))
        if exists:
            return
        db.add(PCComponent(
            component_type="gpu", brand="TestBrand", model="GAMETEST 4060",
            benchmark_score=10000, avg_price=4_600_000, sample_count=10,
        ))
        db.commit()


def test_game_flow(client):
    _seed_components()
    r = client.get("/api/v1/game/question")
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["question_id"]
    assert q["product"]
    assert "4600000" not in q["product"] and "4.600" not in q["specs"]
    # submit exact guess -> score 100
    r = client.post("/api/v1/game/submit", json={"question_id": q["question_id"], "guess_idr": 4600000})
    if r.status_code == 200 and r.json()["actual_price"] == 4600000:
        assert r.json()["score"] == 100
        assert r.json()["difference"] == 0
    # tampered question id -> 400
    r = client.post("/api/v1/game/submit", json={"question_id": "tampered.payload", "guess_idr": 1})
    assert r.status_code == 400


def test_game_scoring_formula(client):
    _seed_components()
    r = client.get("/api/v1/game/question")
    qid = r.json()["question_id"]
    r = client.post("/api/v1/game/submit", json={"question_id": qid, "guess_idr": 2300000})
    body = r.json()
    if body["actual_price"] == 4600000:
        # |2.3jt - 4.6jt| / 4.6jt = 50% -> score 50
        assert body["score"] == 50
        assert body["difference"] == -2300000


# ---------------- B9: currency, feedback, profile ----------------

def test_currency_rates(client):
    r = client.get("/api/v1/currency/rates", params={"base": "IDR"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["base"] == "IDR"
    assert set(body["rates"]) >= {"USD", "SGD", "MYR"}
    assert all(v > 0 for v in body["rates"].values())


def test_feedback(client):
    _register(client, email="fb@x.com")
    headers, _ = _auth_headers(client, email="fb@x.com")
    # empty kesan+saran rejected
    r = client.post("/api/v1/feedback", json={"rating": 5, "kesan": "", "saran": ""}, headers=headers)
    assert r.status_code == 422
    r = client.post(
        "/api/v1/feedback",
        json={"rating": 5, "kesan": "Mantap", "saran": "Tambah dark mode"},
        headers=headers,
    )
    assert r.status_code == 201
    assert "id" in r.json()
    # bad rating rejected
    r = client.post("/api/v1/feedback", json={"rating": 9, "kesan": "x", "saran": "y"}, headers=headers)
    assert r.status_code == 422


def test_profile_update_and_photo(client):
    _register(client, email="prof@x.com", name="Old Name")
    headers, _ = _auth_headers(client, email="prof@x.com")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = client.put(
        "/api/v1/users/me",
        data={"name": "New Name"},
        files={"photo": ("avatar.png", io.BytesIO(png), "image/png")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New Name"
    assert body["photo_url"].startswith("/api/v1/files/profile_photos/user_")
    r = client.get(body["photo_url"])
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")
    # non-image rejected
    r = client.put(
        "/api/v1/users/me",
        files={"photo": ("evil.txt", io.BytesIO(b"hi"), "text/plain")},
        headers=headers,
    )
    assert r.status_code == 422


# ---------------- existing endpoints unaffected ----------------

def test_existing_endpoints_still_work(client):
    assert client.get("/health").status_code == 200
    r = client.get("/api/v1/freshness")
    assert r.status_code == 200
    r = client.get("/api/v1/suggest/pc", params={"q": "RTX"})
    assert r.status_code == 200
    assert r.json()["section"] == "pc"
