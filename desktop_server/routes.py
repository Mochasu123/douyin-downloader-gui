"""FastAPI REST + WebSocket routes for the DouyinDownloader desktop UI."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from desktop_server.state import DesktopRuntime, default_download_dir

_ALLOWED_IMAGE_HOST_SUFFIXES = (
    "douyinpic.com",
    "douyincdn.com",
    "douyinstatic.com",
    "douyinvod.com",
    "bytedance.com",
    "bytegecko.com",
    "byteimg.com",
    "ibytedtos.com",
    "bytetos.com",
    "bytevcloudapi.com",
    "bytecdn.cn",
    "byteicdn.com",
    "amemv.com",
    "snssdk.com",
    "toutiao.com",
    "toutiaovod.com",
    "pstatp.com",
    "iesdouyin.com",
    "douyin.com",
    "zjcdn.com",
    "ixigua.com",
    "volccdn.com",
    "vlabvod.com",
    "vlabstatic.com",
)


def _is_allowed_image_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_IMAGE_HOST_SUFFIXES)


def _find_aweme_local_files(base_path: Path, aweme_id: str) -> List[Path]:
    """Find local media/metadata files belonging to ``aweme_id`` under ``base_path``."""
    if not base_path.exists():
        return []
    if base_path.is_file():
        return [base_path]
    if not base_path.is_dir():
        return []

    found: Dict[Path, Path] = {}

    def _add(file_path: Path) -> None:
        if file_path.is_file():
            try:
                key = file_path.resolve()
            except OSError:
                key = file_path
            found[key] = file_path

    aid = str(aweme_id or "").strip()
    if aid and aid in base_path.name:
        for f in base_path.rglob("*"):
            _add(f)
        return sorted(found.values(), key=lambda p: str(p))

    if not aid:
        return []

    for sub in base_path.rglob("*"):
        if sub.is_dir() and aid in sub.name:
            for f in sub.rglob("*"):
                _add(f)
    for f in base_path.rglob(f"*{aid}*"):
        _add(f)
    return sorted(found.values(), key=lambda p: str(p))


def _pick_primary_aweme_file(files: List[Path], aweme_type: str, fallback: Path) -> str:
    """Choose the best representative local file for quick-open/reveal actions."""
    if not files:
        return ""
    is_gallery = aweme_type == "gallery"
    media_exts = (
        (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mp3")
        if is_gallery
        else (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".mp3")
    )
    if is_gallery:
        merged_images = [
            f
            for f in files
            if "合成动图" in f.parts and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        ]
        if merged_images:
            return str(merged_images[0])
    for ext in media_exts:
        matches = [f for f in files if f.suffix.lower() == ext]
        if matches:
            return str(matches[0])
    return str(files[0] if files else fallback)


def _protected_download_roots(runtime: DesktopRuntime) -> set[Path]:
    roots: set[Path] = set()
    candidates = [runtime.project_root]
    try:
        cfg = runtime.build_config_loader()
        dl_path = str(cfg.get("path") or default_download_dir()).strip()
        if dl_path:
            p = Path(dl_path)
            if not p.is_absolute():
                p = runtime.project_root / p
            candidates.append(p)
    except Exception:
        pass
    for c in candidates:
        try:
            resolved = c.resolve()
            roots.add(resolved)
            if resolved.parent:
                roots.add(resolved.parent)
        except OSError:
            pass
    return roots


def _delete_aweme_local_files(
    base_path: Path, aweme_id: str, protected_roots: set[Path]
) -> int:
    """Delete local files for ``aweme_id`` safely, including nested subfolders."""
    if not base_path.exists():
        return 0
    try:
        resolved_base = base_path.resolve()
    except OSError:
        resolved_base = base_path

    if resolved_base == resolved_base.parent:
        return 0
    if base_path.is_file():
        base_path.unlink(missing_ok=True)
        return 1
    if not base_path.is_dir():
        return 0

    aid = str(aweme_id or "").strip()
    deleted_count = 0

    if aid and aid in base_path.name and resolved_base not in protected_roots:
        deleted_count = sum(1 for f in base_path.rglob("*") if f.is_file())
        shutil.rmtree(base_path, ignore_errors=True)
        return deleted_count

    if not aid:
        return 0

    # 1. Remove any dedicated subfolder matching *{aweme_id}* (deepest first)
    matching_dirs = sorted(
        (d for d in base_path.rglob("*") if d.is_dir() and aid in d.name),
        key=lambda d: len(d.parts),
        reverse=True,
    )
    for d in matching_dirs:
        if not d.exists():
            continue
        try:
            if d.resolve() in protected_roots:
                continue
        except OSError:
            continue
        deleted_count += sum(1 for f in d.rglob("*") if f.is_file())
        shutil.rmtree(d, ignore_errors=True)

    # 2. Remove any files referencing *{aweme_id}* across root and subfolders (实况素材 / 合成动图 / etc.)
    for f in list(base_path.rglob(f"*{aid}*")):
        if f.is_file():
            f.unlink(missing_ok=True)
            deleted_count += 1

    # 3. Clean up empty subdirectories bottom-up
    all_dirs = sorted(
        (d for d in base_path.rglob("*") if d.is_dir()),
        key=lambda d: len(d.parts),
        reverse=True,
    )
    for d in all_dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    # 4. Remove base_path only if it is now completely empty and not a protected root
    if resolved_base not in protected_roots:
        try:
            if base_path.exists() and not any(base_path.iterdir()):
                base_path.rmdir()
        except OSError:
            pass

    return deleted_count


class CookiePayload(BaseModel):
    cookie: str


class ProxyTestPayload(BaseModel):
    proxy: str = ""


class OpenPathPayload(BaseModel):
    path: str
    reveal: bool = False


class InspectUrlsPayload(BaseModel):
    text: str


class PreviewStartPayload(BaseModel):
    preview_id: Optional[str] = None
    urls: Optional[List[str]] = None
    sec_uid: Optional[str] = None
    mode: str = "post"
    limit: int = 0
    start_time: str = ""
    end_time: str = ""
    increase: Optional[bool] = None
    scope: Optional[str] = None
    append: bool = False
    auto_download: bool = False


class DeleteParseHistoryPayload(BaseModel):
    ids: Optional[List[int]] = None
    scope: Optional[str] = None


class DownloadTaskPayload(BaseModel):
    preview_id: Optional[str] = None
    aweme_ids: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    mode: str = "post"
    title: str = ""
    overrides: Optional[Dict[str, Any]] = None


class LoadCommentsPayload(BaseModel):
    aweme_id: str
    include_replies: bool = False
    max_comments: int = 0


class DownloadCommentImagesPayload(BaseModel):
    aweme_id: str
    keys: List[str]
    save_dir: str = ""


class ExportCommentsPayload(BaseModel):
    aweme_id: str
    output_path: str = ""
    aweme_title: str = ""


class DeleteHistoryPayload(BaseModel):
    aweme_ids: List[str]
    delete_files: bool = False


def build_router(runtime: DesktopRuntime) -> APIRouter:
    router = APIRouter()

    # ── Health ──────────────────────────────────────────────────────────

    @router.get("/api/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "version": "2.1.1-desktop",
            "project_root": str(runtime.project_root),
        }

    # ── Auth ────────────────────────────────────────────────────────────

    @router.get("/api/auth/status")
    async def auth_status(verify: bool = False) -> Dict[str, Any]:
        return await runtime.get_auth_status(verify=verify)

    @router.post("/api/auth/cookie")
    async def save_cookie(payload: CookiePayload) -> Dict[str, Any]:
        runtime.save_cookie_string(payload.cookie)
        return await runtime.get_auth_status(verify=True)

    @router.post("/api/auth/browser-login/start")
    async def browser_login_start() -> Dict[str, Any]:
        return await runtime.start_browser_login()

    @router.post("/api/auth/browser-login/extract")
    async def browser_login_extract() -> Dict[str, Any]:
        return runtime.trigger_browser_login_extract()

    @router.post("/api/auth/browser-login/cancel")
    async def browser_login_cancel() -> Dict[str, Any]:
        return runtime.cancel_browser_login()

    # ── Settings & System ───────────────────────────────────────────────

    @router.get("/api/settings")
    async def get_settings() -> Dict[str, Any]:
        return runtime.get_settings_payload()

    @router.put("/api/settings")
    async def put_settings(request: Request) -> Dict[str, Any]:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid settings payload")
        return runtime.save_settings_payload(body)

    @router.post("/api/settings/test-proxy")
    async def test_proxy(payload: ProxyTestPayload) -> Dict[str, Any]:
        proxy = (payload.proxy or "").strip() or None
        started = time.monotonic()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as sess:
                async with sess.get(
                    "https://www.douyin.com/",
                    proxy=proxy,
                    headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=False,
                ) as resp:
                    ms = int((time.monotonic() - started) * 1000)
                    return {"ok": resp.status < 500, "status": resp.status, "latency_ms": ms}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "latency_ms": 0}

    @router.post("/api/system/open-path")
    async def open_path(payload: OpenPathPayload) -> Dict[str, Any]:
        raw = (payload.path or "").strip()
        target = Path(raw) if raw else Path(default_download_dir())
        if not target.exists():
            if payload.reveal and target.parent.exists():
                target = target.parent
            else:
                target.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                if payload.reveal and target.is_file():
                    subprocess.Popen(["explorer", f"/select,{target}"])
                else:
                    os.startfile(str(target))
            return {"ok": True, "path": str(target)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── URL Inspection & Preview ────────────────────────────────────────

    @router.post("/api/urls/inspect")
    async def inspect_urls(payload: InspectUrlsPayload) -> Dict[str, Any]:
        return {"urls": runtime.inspect_urls_text(payload.text)}

    @router.post("/api/preview/start")
    async def preview_start(payload: PreviewStartPayload) -> Dict[str, Any]:
        preview_id = runtime.start_preview(
            preview_id=payload.preview_id,
            urls=payload.urls,
            sec_uid=payload.sec_uid,
            mode=payload.mode,
            limit=payload.limit,
            start_time=payload.start_time,
            end_time=payload.end_time,
            increase=payload.increase,
            scope=payload.scope,
            append=payload.append,
            auto_download=payload.auto_download,
        )
        return {"preview_id": preview_id}

    @router.post("/api/preview/cancel/{preview_id}")
    async def preview_cancel(preview_id: str) -> Dict[str, Any]:
        return {"cancelled": runtime.cancel_preview(preview_id)}

    @router.get("/api/preview/workspace")
    async def preview_workspace() -> Dict[str, Any]:
        return runtime.get_preview_workspace_payload()

    @router.delete("/api/preview/workspace/{scope}")
    async def clear_preview_workspace(scope: str) -> Dict[str, Any]:
        if scope not in ("link", "creator"):
            raise HTTPException(status_code=400, detail="Invalid workspace scope")
        return {"cleared": runtime.clear_preview_workspace(scope)}

    @router.delete("/api/preview/workspace/{scope}/item/{aweme_id}")
    async def remove_preview_workspace_item(scope: str, aweme_id: str) -> Dict[str, Any]:
        if scope not in ("link", "creator"):
            raise HTTPException(status_code=400, detail="Invalid workspace scope")
        return {"removed": runtime.remove_preview_workspace_item(scope, aweme_id)}

    @router.get("/api/preview/history")
    async def preview_history(scope: str = Query("link")) -> Dict[str, Any]:
        if runtime.db is None:
            return {"items": []}
        kinds = ["user"] if scope == "user" else ["video", "gallery", "collection", "music"]
        rows = await runtime.db.list_parse_history(kinds=kinds, limit=200)
        return {"items": rows}

    @router.delete("/api/preview/history")
    async def delete_preview_history(payload: DeleteParseHistoryPayload) -> Dict[str, Any]:
        if runtime.db is None:
            return {"deleted": 0}
        if payload.ids:
            deleted = await runtime.db.delete_parse_history(payload.ids)
            return {"deleted": deleted}
        if payload.scope:
            kinds = ["user"] if payload.scope == "user" else ["video", "gallery", "collection", "music"]
            total = 0
            for k in kinds:
                total += await runtime.db.clear_parse_history(k)
            return {"deleted": total}
        return {"deleted": 0}

    @router.get("/api/preview/{preview_id}/item/{aweme_id}/media")
    async def preview_item_media(
        preview_id: str,
        aweme_id: str,
        refresh: bool = Query(False),
    ) -> Dict[str, Any]:
        try:
            return await runtime.get_preview_item_media(preview_id, aweme_id, refresh=refresh)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/api/preview/{preview_id}")
    async def preview_session(preview_id: str) -> Dict[str, Any]:
        sess = runtime.preview_sessions.get(preview_id)
        if not sess:
            raise HTTPException(status_code=404, detail="preview not found")
        return {
            "preview_id": sess["preview_id"],
            "status": sess["status"],
            "meta": sess.get("meta"),
            "items": [it.to_summary_dict() for it in sess["items"]],
        }

    # ── Download Tasks ──────────────────────────────────────────────────

    @router.post("/api/tasks/download")
    async def create_download_task(payload: DownloadTaskPayload) -> Dict[str, Any]:
        try:
            job = runtime.submit_download_job(
                preview_id=payload.preview_id,
                aweme_ids=payload.aweme_ids,
                urls=payload.urls,
                mode=payload.mode,
                title=payload.title,
                overrides=payload.overrides,
            )
            return {"job": job}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/tasks")
    async def get_tasks() -> Dict[str, Any]:
        return {"jobs": runtime.list_jobs()}

    @router.post("/api/tasks/{job_id}/pause")
    async def pause_task(job_id: str) -> Dict[str, Any]:
        if not runtime.pause_job(job_id):
            raise HTTPException(status_code=400, detail="无法暂停当前任务")
        return {"ok": True}

    @router.post("/api/tasks/{job_id}/resume")
    async def resume_task(job_id: str) -> Dict[str, Any]:
        if not runtime.resume_job(job_id):
            raise HTTPException(status_code=400, detail="无法恢复当前任务")
        return {"ok": True}

    @router.post("/api/tasks/{job_id}/cancel")
    async def cancel_task(job_id: str) -> Dict[str, Any]:
        if not runtime.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"ok": True}

    @router.post("/api/tasks/{job_id}/retry-failed")
    async def retry_task_failed(job_id: str) -> Dict[str, Any]:
        try:
            job = runtime.retry_failed_job(job_id)
            return {"job": job}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.delete("/api/tasks/{job_id}")
    async def remove_task(job_id: str) -> Dict[str, Any]:
        if not await runtime.delete_job(job_id):
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"ok": True}

    # ── Comments ────────────────────────────────────────────────────────

    @router.post("/api/comments/load")
    async def comments_load(payload: LoadCommentsPayload) -> Dict[str, Any]:
        try:
            return await runtime.load_comments(
                payload.aweme_id,
                include_replies=payload.include_replies,
                max_comments=payload.max_comments,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/api/comments/download-images")
    async def comments_download_images(payload: DownloadCommentImagesPayload) -> Dict[str, Any]:
        try:
            return await runtime.download_comment_images(
                payload.aweme_id, payload.keys, payload.save_dir
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/api/comments/export-excel")
    async def comments_export_excel(payload: ExportCommentsPayload):
        try:
            if payload.output_path.strip():
                saved = runtime.export_comments_excel(
                    payload.aweme_id, payload.output_path.strip(), payload.aweme_title
                )
                return {"ok": True, "path": saved}
            export_dir = runtime.cache_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = export_dir / f"{payload.aweme_id}_评论.xlsx"
            saved = runtime.export_comments_excel(
                payload.aweme_id, str(tmp_file), payload.aweme_title
            )
            return FileResponse(
                saved,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"{payload.aweme_id}_评论.xlsx",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Download History & Stats ────────────────────────────────────────

    @router.get("/api/history")
    async def get_history(
        page: int = Query(1, ge=1),
        size: int = Query(48, ge=1, le=200),
        q: str = Query(""),
        author: str = Query(""),
        aweme_type: str = Query(""),
        sort: str = Query("download_time"),
    ) -> Dict[str, Any]:
        if runtime.db is None:
            return {"total": 0, "page": page, "size": size, "items": []}
        res = await runtime.db.get_aweme_history(
            page=page,
            size=size,
            author=author.strip() or None,
            aweme_type=aweme_type.strip() or None,
            title=q.strip() or None,
            sort=sort if sort in ("download_time", "create_time") else "download_time",
        )
        items = res.get("items", [])
        for item in items:
            fp = item.get("file_path") or ""
            p = Path(fp) if fp else None
            aid = str(item.get("aweme_id") or "")
            aweme_type = str(item.get("aweme_type") or "")
            primary_file = ""
            local_file_count = 0
            exists = False
            if p is not None and p.exists():
                matched = _find_aweme_local_files(p, aid)
                local_file_count = len(matched)
                exists = local_file_count > 0
                if matched:
                    primary_file = _pick_primary_aweme_file(matched, aweme_type, p)
            item["file_exists"] = exists
            item["local_file_count"] = local_file_count
            item["primary_file"] = primary_file
            covers = item.get("cover_urls") or []
            item["cover_url"] = covers[0] if covers else ""
        return res

    @router.get("/api/history/stats")
    async def get_history_stats() -> Dict[str, Any]:
        if runtime.db is None:
            return {
                "total_count": 0,
                "video_count": 0,
                "gallery_count": 0,
                "music_count": 0,
                "live_count": 0,
                "author_count": 0,
                "recent_7d_count": 0,
                "top_authors": [],
            }
        return await runtime.db.get_history_stats()

    @router.delete("/api/history")
    async def delete_history(payload: DeleteHistoryPayload) -> Dict[str, Any]:
        if runtime.db is None or not payload.aweme_ids:
            return {"deleted": 0, "deleted_files": 0}
        deleted_files = 0
        if payload.delete_files:
            protected = _protected_download_roots(runtime)
            # Look up paths before deleting
            for aid in payload.aweme_ids:
                try:
                    cursor = await (await runtime.db._get_conn()).execute(
                        "SELECT file_path FROM aweme WHERE aweme_id = ?", (aid,)
                    )
                    row = await cursor.fetchone()
                    if row and row[0]:
                        deleted_files += _delete_aweme_local_files(
                            Path(row[0]), str(aid), protected
                        )
                except Exception:
                    pass
        deleted = await runtime.db.delete_aweme_by_ids(payload.aweme_ids)
        return {"deleted": deleted, "deleted_files": deleted_files}

    # ── Image Proxy & Local Avatar ──────────────────────────────────────

    @router.get("/api/proxy/image")
    async def proxy_image(url: str = Query(...)):
        if not _is_allowed_image_url(url):
            raise HTTPException(status_code=403, detail="Disallowed image host")

        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        cache_file = runtime.thumb_cache_dir / digest
        meta_file = runtime.thumb_cache_dir / f"{digest}.ctype"

        if cache_file.exists() and cache_file.stat().st_size > 0:
            ctype = (
                meta_file.read_text(encoding="utf-8").strip()
                if meta_file.exists()
                else "image/jpeg"
            )
            return Response(
                content=cache_file.read_bytes(),
                media_type=ctype or "image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

        if runtime.http_session is None or runtime.http_session.closed:
            raise HTTPException(status_code=503, detail="HTTP session unavailable")

        cfg = runtime.build_config_loader()
        proxy = (cfg.get("proxy") or "").strip() or None
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        try:
            async with runtime.http_session.get(url, headers=headers, proxy=proxy) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Upstream image error")
                ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
                data = await resp.read()
                if not data or len(data) > 15 * 1024 * 1024:
                    raise HTTPException(status_code=502, detail="Invalid image size")
                try:
                    cache_file.write_bytes(data)
                    meta_file.write_text(ctype, encoding="utf-8")
                except OSError:
                    pass
                return Response(
                    content=data,
                    media_type=ctype,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/api/proxy/media")
    async def proxy_media(request: Request, url: str = Query(...)):
        if not _is_allowed_image_url(url):
            raise HTTPException(status_code=403, detail="Disallowed media host")
        if runtime.http_session is None or runtime.http_session.closed:
            raise HTTPException(status_code=503, detail="HTTP session unavailable")

        cfg = runtime.build_config_loader()
        proxy = (cfg.get("proxy") or "").strip() or None
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
        }
        incoming_range = request.headers.get("range")
        if incoming_range:
            headers["Range"] = incoming_range

        try:
            resp = await runtime.http_session.get(
                url,
                headers=headers,
                proxy=proxy,
                allow_redirects=True,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if resp.status not in (200, 206):
            status_code = resp.status
            await resp.release()
            raise HTTPException(status_code=status_code, detail="Upstream media error")

        out_headers: Dict[str, str] = {"Accept-Ranges": "bytes"}
        for key in ("Content-Length", "Content-Range"):
            val = resp.headers.get(key)
            if val:
                out_headers[key] = val
        media_type = (resp.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()

        async def _stream():
            try:
                async for chunk in resp.content.iter_chunked(65536):
                    if chunk:
                        yield chunk
            finally:
                await resp.release()

        return StreamingResponse(
            _stream(),
            status_code=resp.status,
            media_type=media_type,
            headers=out_headers,
        )

    @router.get("/api/local-avatar/{sec_uid}")
    async def local_avatar(sec_uid: str):
        safe_id = "".join(c for c in sec_uid if c.isalnum() or c in "-_")
        if not safe_id:
            raise HTTPException(status_code=404, detail="Avatar not found")
        path = runtime.avatar_cache_dir / f"{safe_id}.jpg"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Avatar not found")
        return FileResponse(str(path), media_type="image/jpeg")

    # ── Logs & WebSocket ────────────────────────────────────────────────

    @router.get("/api/logs")
    async def get_logs() -> Dict[str, Any]:
        return {"logs": runtime.event_bus.get_logs()}

    @router.delete("/api/logs")
    async def clear_logs() -> Dict[str, Any]:
        runtime.event_bus.clear_logs()
        return {"ok": True}

    @router.websocket("/ws/events")
    async def ws_events(websocket: WebSocket):
        await runtime.event_bus.connect(websocket)
        try:
            while True:
                # Keep connection alive; handle ping/pong or client acks
                await websocket.receive_text()
        except WebSocketDisconnect:
            runtime.event_bus.disconnect(websocket)
        except Exception:
            runtime.event_bus.disconnect(websocket)

    return router
