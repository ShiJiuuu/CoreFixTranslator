from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import api, db
from .config import default_data_dir
from .worker import TranslationWorker

DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    configured = os.environ.get("DATA_DIR", "").strip()
    if configured:
        data_dir = Path(configured).expanduser()
        if not data_dir.is_absolute():
            data_dir = (Path(__file__).resolve().parents[2] / data_dir).resolve()
    else:
        data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.getLogger("corefix").info("data_dir=%s db=%s", data_dir, data_dir / "app.db")
    db.init_db(data_dir / "app.db")
    api.configure(data_dir)
    worker = TranslationWorker(data_dir)
    worker.start()
    app.state.worker = worker
    try:
        yield
    finally:
        worker.stop()
        worker.join(timeout=5)


app = FastAPI(title="CoreFix Document Translator", version="0.2.0", lifespan=lifespan)
app.include_router(api.router)

if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


@app.get("/favicon.ico")
def favicon() -> Response:
    icon = DIST_DIR / "favicon.svg"
    if icon.exists():
        return FileResponse(icon)
    return Response(status_code=204)


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api/") or full_path in ("healthz", "readyz"):
        raise HTTPException(status_code=404, detail="not found")
    index = DIST_DIR / "index.html"
    if index.exists():
        return FileResponse(index, media_type="text/html")
    return JSONResponse(
        {"error": "frontend_not_built", "hint": "cd frontend && npm install && npm run build"},
        status_code=503,
    )
