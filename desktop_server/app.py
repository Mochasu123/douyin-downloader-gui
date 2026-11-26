"""FastAPI application factory serving API, WebSocket, and built React SPA."""

from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from desktop_server.routes import build_router
from desktop_server.state import DesktopRuntime


def create_app(
    project_root: Path,
    *,
    frontend_dist: Optional[Path] = None,
) -> FastAPI:
    runtime = DesktopRuntime(project_root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.startup_error = None
        try:
            await runtime.startup()
        except BaseException:
            app.state.startup_error = traceback.format_exc()
            raise
        try:
            yield
        finally:
            await runtime.shutdown()

    app = FastAPI(
        title="DouyinDownloader Desktop Backend",
        version="2.1.1",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.include_router(build_router(runtime))

    dist_dir = frontend_dist or (Path(project_root) / "frontend" / "dist")
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        index_html = dist_dir / "index.html"

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith(("api/", "ws/")):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = (dist_dir / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and dist_dir.resolve() in candidate.parents
            ):
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))
    else:

        @app.get("/")
        async def placeholder_index():
            return HTMLResponse(
                "<html><body><h3>Frontend build not found (frontend/dist).</h3></body></html>",
                status_code=200,
            )

    return app
