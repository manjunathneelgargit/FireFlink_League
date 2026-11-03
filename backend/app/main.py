from pathlib import Path

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401 - register tables
from .api.routes import router
from .db import Base, SessionLocal, engine
from .services import gsheet

Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(_app):
    # One background worker mirrors the Google Sheet (run a single server process, or set
    # DISABLE_GSHEET_SYNC=1 on all but one process).
    if os.environ.get("DISABLE_GSHEET_SYNC") != "1":
        gsheet.start_worker(SessionLocal)
    yield


app = FastAPI(title="FireFlink 4.0 League Tracker", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, 404)
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
