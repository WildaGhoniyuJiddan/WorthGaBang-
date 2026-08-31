"""Vercel serverless entrypoint for the FastAPI app (via Mangum)."""
from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="off")
