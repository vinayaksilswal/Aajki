"""Deployment entry point (Vercel's Python runtime and `uvicorn main:app`)."""
from app.main import create_app

app = create_app()
