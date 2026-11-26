"""Tests for the embedded FastAPI + WebSocket desktop backend (desktop_server)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core.preview_service import PreviewItem
from desktop_server.app import create_app


@pytest.fixture
def desktop_client(tmp_path: Path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>DouyinUI</body></html>", encoding="utf-8")
    (tmp_path / "config.example.yml").write_text(
        "path: ./Downloaded/\nthread: 5\nvideo_quality: highest\n",
        encoding="utf-8",
    )
    app = create_app(tmp_path, frontend_dist=dist)
    with TestClient(app) as client:
        yield client, app, tmp_path


def test_health_and_spa_root(desktop_client):
    client, _app, _root = desktop_client
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "DouyinUI" in home.text


def test_settings_roundtrip_preserves_all_fields(desktop_client):
    client, _app, root = desktop_client
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "config" in data
    assert "cookie" in data
    assert "preferences" in data

    updated = client.put(
        "/api/settings",
        json={
            "config": {
                "path": str(root / "MyDl"),
                "thread": 4,
                "proxy": "http://127.0.0.1:7897",
                "video_quality": "original",
                "live_photo_merge": False,
                "comments": {
                    "enabled": True,
                    "include_replies": True,
                    "max_comments": 50,
                    "page_size": 20,
                    "download_media": True,
                },
            },
            "cookie_raw": "sessionid=abc123; odin_tt=xyz; passport_csrf_token=tok",
            "preferences": {"theme": "dark", "view_mode": "table"},
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["config"]["thread"] == 4
    assert payload["config"]["proxy"] == "http://127.0.0.1:7897"
    assert payload["config"]["video_quality"] == "original"
    assert payload["config"]["live_photo_merge"] is False
    assert payload["config"]["comments"]["download_media"] is True
    assert payload["cookie"]["has_cookie"] is True
    assert payload["cookie"]["count"] == 3
    assert payload["preferences"]["theme"] == "dark"
    assert payload["preferences"]["view_mode"] == "table"

    # Re-read from disk via fresh GET
    res2 = client.get("/api/settings")
    assert res2.status_code == 200
    assert res2.json()["config"]["video_quality"] == "original"
    assert res2.json()["config"]["proxy"] == "http://127.0.0.1:7897"


def test_inspect_urls_extracts_share_text_and_dedupes(desktop_client):
    client, _app, _root = desktop_client
    raw = (
        "8.88 复制打开抖音 https://www.douyin.com/video/7400000000000000001 看看\n"
        "https://www.douyin.com/video/7400000000000000001\n"
        "https://www.douyin.com/user/MS4wLjABAAAA12345\n"
        "https://v.douyin.com/abcdef/\n"
    )
    res = client.post("/api/urls/inspect", json={"text": raw})
    assert res.status_code == 200
    urls = res.json()["urls"]
    assert [u["type"] for u in urls] == ["video", "user", "short"]


def test_image_proxy_blocks_non_douyin_hosts(desktop_client):
    client, _app, _root = desktop_client
    r1 = client.get("/api/proxy/image", params={"url": "https://example.com/evil.png"})
    assert r1.status_code == 403
    r2 = client.get("/api/proxy/image", params={"url": "http://127.0.0.1:8080/secret"})
    assert r2.status_code == 403


def test_history_and_stats_endpoints(desktop_client):
    client, app, _root = desktop_client
    runtime = app.state.runtime

    async def _seed():
        await runtime.db.add_aweme(
            {
                "aweme_id": "111",
                "aweme_type": "video",
                "title": "测试视频A",
                "author_id": "u1",
                "author_name": "博主甲",
                "author_sec_uid": "sec_1",
                "create_time": 1700000000,
                "file_path": str(runtime.project_root),
                "metadata": "{}",
            }
        )
        await runtime.db.add_parse_history(
            {
                "kind": "video",
                "content_id": "111",
                "name": "测试视频A",
                "original_url": "https://www.douyin.com/video/111",
                "resolved_url": "https://www.douyin.com/video/111",
                "author_name": "博主甲",
            }
        )

    asyncio.run(_seed())

    hist = client.get("/api/history")
    assert hist.status_code == 200
    assert hist.json()["total"] == 1
    assert hist.json()["items"][0]["title"] == "测试视频A"

    stats = client.get("/api/history/stats")
    assert stats.status_code == 200
    assert stats.json()["total_count"] == 1
    assert stats.json()["video_count"] == 1
    assert stats.json()["top_authors"][0]["author_name"] == "博主甲"

    ph = client.get("/api/preview/history", params={"scope": "link"})
    assert ph.status_code == 200
    assert len(ph.json()["items"]) == 1


def test_tasks_download_validation_and_websocket_logs(desktop_client):
    client, app, _root = desktop_client
    bad = client.post("/api/tasks/download", json={})
    assert bad.status_code == 400

    runtime = app.state.runtime
    runtime.preview_sessions["p1"] = {
        "preview_id": "p1",
        "items": [
            PreviewItem(
                aweme_id="999",
                title="示例",
                publish_time="2026-11-25 10:00:00",
                duration="00:15",
                media_type="视频",
                author_name="测试作者",
                author_sec_uid="sec_9",
                size_text="1.0 MB",
                source_type="video",
                raw={"aweme_id": "999", "desc": "示例"},
            )
        ],
        "by_id": {},
        "status": "done",
    }
    runtime.preview_sessions["p1"]["by_id"]["999"] = runtime.preview_sessions["p1"]["items"][0]

    # Mock job execution so test doesn't hit network
    runtime._run_items_job = AsyncMock(return_value=None)
    created = client.post(
        "/api/tasks/download",
        json={"preview_id": "p1", "aweme_ids": ["999"]},
    )
    assert created.status_code == 200
    job = created.json()["job"]
    assert job["total"] == 1

    tasks = client.get("/api/tasks")
    assert tasks.status_code == 200
    assert any(j["job_id"] == job["job_id"] for j in tasks.json()["jobs"])

    with client.websocket_connect("/ws/events") as ws:
        # Initial snapshot or ping
        runtime.event_bus.append_log("INFO", "Test", "hello ws")
        msg = ws.receive_json()
        assert msg["type"] in ("logs_snapshot", "log")


def test_native_bridge_hides_window_from_pywebview_introspection():
    import desktop_app

    class ExplodingWindow:
        @property
        def width(self):
            raise AssertionError("pywebview must not introspect window GUI properties")

    bridge = desktop_app.NativeBridge()
    bridge._attach_window(ExplodingWindow())

    assert not hasattr(bridge, "window")
    assert not hasattr(bridge, "attach_window")

    public_attrs = {name for name in dir(bridge) if not name.startswith("_")}
    assert public_attrs == {
        "pick_directory",
        "save_file_dialog",
        "open_path",
        "reveal_in_explorer",
        "read_clipboard",
    }
    assert all(callable(getattr(bridge, name)) for name in public_attrs)
    assert bridge._run_on_ui_thread(lambda: "ok") == "ok"


def test_desktop_page_bridge_query_sanitization_and_wiring(tmp_path):
    import asyncio
    from auth import CookieManager
    from config import ConfigLoader
    from core import DouyinAPIClient
    from core.preview_service import PreviewService
    from desktop_server.page_bridge import DesktopPageBridge, PageBridgeResponse
    from desktop_server.state import DesktopRuntime

    url = DesktopPageBridge.build_request_url(
        "/aweme/v1/web/aweme/detail/",
        {
            "aweme_id": "7712005420173470331",
            "aid": "6383",
            "uifid": "",
            "msToken": "",
            "a_bogus": "stale_ab",
            "X-Bogus": "stale_xb",
        },
    )
    assert "aweme_id=7712005420173470331" in url
    assert "aid=6383" in url
    assert "uifid" not in url
    assert "msToken" not in url
    assert "a_bogus" not in url
    assert "X-Bogus" not in url

    class FakeBridge:
        def __init__(self):
            self.calls = []

        async def fetch(self, path, params, *, method="GET", data=None):
            self.calls.append((path, dict(params), method))
            return PageBridgeResponse(
                http_status=200,
                body={
                    "status_code": 0,
                    "aweme_detail": {
                        "aweme_id": "7712005420173470331",
                        "aweme_type": 68,
                        "desc": "测试实况图集",
                    },
                },
            )

    async def _run():
        cfg = ConfigLoader(None)
        cfg.config["path"] = str(tmp_path)
        cm = CookieManager(str(tmp_path / ".cookies.json"))
        fake_bridge = FakeBridge()
        service = PreviewService(cfg, cm, page_bridge=fake_bridge)
        try:
            assert service.api_client.page_bridge is fake_bridge
            detail = await service.api_client.get_video_detail("7712005420173470331")
            assert detail is not None
            assert detail["aweme_id"] == "7712005420173470331"
            assert fake_bridge.calls and fake_bridge.calls[0][0] == "/aweme/v1/web/aweme/detail/"
        finally:
            await service.close()

        runtime = DesktopRuntime(tmp_path)
        runtime.page_bridge._applied_cookie_fingerprint = (("k", "v"),)
        runtime.save_cookie_string("sessionid=abc; odin_tt=xyz")
        assert runtime.page_bridge._applied_cookie_fingerprint is None
        await runtime.page_bridge.close()

    asyncio.run(_run())


def test_wait_for_health_fails_fast_and_bypasses_proxy(monkeypatch):
    import threading
    import time
    import urllib.request
    import desktop_app

    dead_thread = threading.Thread(target=lambda: None)
    dead_thread.start()
    dead_thread.join()

    built_handlers = []
    orig_build_opener = urllib.request.build_opener

    def _spy_build_opener(*handlers):
        built_handlers.extend(handlers)
        return orig_build_opener(*handlers)

    monkeypatch.setattr(urllib.request, "build_opener", _spy_build_opener)

    unused_port = desktop_app._find_free_port()
    started = time.monotonic()
    ok = desktop_app._wait_for_health(unused_port, timeout=10.0, server_thread=dead_thread)
    elapsed = time.monotonic() - started

    assert ok is False
    assert elapsed < 3.0
    assert any(
        isinstance(h, urllib.request.ProxyHandler) and h.proxies == {}
        for h in built_handlers
    )


def test_workspace_persistence_media_detail_and_proxy_guard(desktop_client):
    from core.preview_service import PreviewItem
    from desktop_server.app import create_app
    from fastapi.testclient import TestClient

    client, app, root = desktop_client
    runtime = app.state.runtime

    # 1. Populate ws_link and save to disk
    sess = runtime.preview_sessions["ws_link"]
    item = PreviewItem(
        aweme_id="7712005420173470399",
        title="持久化实况测试",
        publish_time="2026-11-26 10:00:00",
        duration="未知",
        media_type="图文",
        author_name="测试作者",
        author_sec_uid="sec_test",
        size_text="未知",
        source_type="单个作品",
        cover_url="https://p3-sign.douyinpic.com/cover.jpg",
        raw={
            "aweme_id": "7712005420173470399",
            "aweme_type": 68,
            "desc": "持久化实况测试",
            "music": {"title": "测试背景乐", "play_url": {"url_list": ["https://sf3-cdn-tos.douyinstatic.com/bgm.mp3"]}},
            "images": [
                {
                    "width": 1080,
                    "height": 1440,
                    "url_list": ["https://p3-sign.douyinpic.com/still_1.jpg"],
                    "video": {"play_addr": {"url_list": ["https://v3-web.douyinvod.com/live_1.mp4"]}},
                },
                {
                    "width": 1080,
                    "height": 1440,
                    "url_list": ["https://p3-sign.douyinpic.com/still_2.jpg"],
                },
            ],
        },
    )
    sess["items"] = [item]
    sess["by_id"] = {item.aweme_id: item}
    runtime._save_preview_workspace()
    assert runtime.workspace_cache_path.exists()

    # 2. Verify media detail endpoint extracts slides + live video + BGM without network refresh
    media_resp = client.get("/api/preview/ws_link/item/7712005420173470399/media")
    assert media_resp.status_code == 200
    payload = media_resp.json()
    assert payload["aweme_id"] == "7712005420173470399"
    assert len(payload["slides"]) == 2
    assert payload["slides"][0]["is_live"] is True
    assert payload["slides"][0]["live_video_url"] == "https://v3-web.douyinvod.com/live_1.mp4"
    assert payload["slides"][1]["is_live"] is False
    assert payload["music_title"] == "测试背景乐"
    assert "bgm.mp3" in payload["music_url"]

    # 3. Proxy guard rejects non-Douyin hosts
    bad_proxy = client.get("/api/proxy/media", params={"url": "https://evil.example.com/x.mp4"})
    assert bad_proxy.status_code == 403

    # 4. Restart a fresh app against the same root and verify workspace restored
    app2 = create_app(root)
    with TestClient(app2) as client2:
        ws_resp = client2.get("/api/preview/workspace")
        assert ws_resp.status_code == 200
        ws_data = ws_resp.json()
        assert len(ws_data["link"]["items"]) == 1
        assert ws_data["link"]["items"][0]["aweme_id"] == "7712005420173470399"
        # Media detail still works immediately after restart!
        media2 = client2.get("/api/preview/ws_link/item/7712005420173470399/media")
        assert media2.status_code == 200
        assert len(media2.json()["slides"]) == 2

        # 5. Remove item & clear workspace endpoints
        rm_resp = client2.delete("/api/preview/workspace/link/item/7712005420173470399")
        assert rm_resp.status_code == 200 and rm_resp.json()["removed"] is True
        assert client2.get("/api/preview/workspace").json()["link"]["items"] == []

        clr_resp = client2.delete("/api/preview/workspace/creator")
        assert clr_resp.status_code == 200 and clr_resp.json()["cleared"] is True


def test_start_preview_append_and_auto_download(desktop_client, monkeypatch):
    import asyncio
    from core.preview_service import PreviewItem, PreviewResult, PreviewService

    client, app, _root = desktop_client
    runtime = app.state.runtime

    existing = PreviewItem(
        aweme_id="100",
        title="已存在作品",
        publish_time="2026-11-25 10:00:00",
        duration="00:10",
        media_type="视频",
        author_name="作者A",
        author_sec_uid="secA",
        size_text="1 MB",
        source_type="单个作品",
        raw={"aweme_id": "100"},
    )
    runtime.preview_sessions["ws_link"]["items"] = [existing]
    runtime.preview_sessions["ws_link"]["by_id"] = {"100": existing}

    new_item = PreviewItem(
        aweme_id="200",
        title="新解析实况",
        publish_time="2026-11-26 10:00:00",
        duration="未知",
        media_type="图文",
        author_name="作者B",
        author_sec_uid="secB",
        size_text="未知",
        source_type="单个作品",
        raw={"aweme_id": "200", "aweme_type": 68},
    )

    async def _fake_classify(self, url):
        return url, {"type": "gallery", "aweme_id": "200"}

    async def _fake_preview(self, url, mode="post", *, on_item=None):
        if on_item:
            res = on_item(new_item)
            if asyncio.iscoroutine(res):
                await res
        return PreviewResult(
            source=url,
            source_type="gallery",
            author_name="作者B",
            items=[new_item],
            url_type="gallery",
        )

    monkeypatch.setattr(PreviewService, "classify_url", _fake_classify)
    monkeypatch.setattr(PreviewService, "preview_url", _fake_preview)

    submitted = []
    orig_submit = runtime.submit_download_job

    def _spy_submit(*, preview_id=None, aweme_ids=None, **kwargs):
        submitted.append((preview_id, list(aweme_ids or [])))
        return {"job_id": "j_auto", "total": len(aweme_ids or [])}

    monkeypatch.setattr(runtime, "submit_download_job", _spy_submit)
    try:
        resp = client.post(
            "/api/preview/start",
            json={
                "preview_id": "ws_link",
                "scope": "link",
                "append": True,
                "auto_download": True,
                "urls": ["https://www.douyin.com/note/200"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["preview_id"] == "ws_link"

        import time

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            status_resp = client.get("/api/preview/ws_link")
            if status_resp.status_code == 200 and status_resp.json().get("status") == "done":
                break
            time.sleep(0.05)
    finally:
        monkeypatch.setattr(runtime, "submit_download_job", orig_submit)

    items = runtime.preview_sessions["ws_link"]["items"]
    assert [it.aweme_id for it in items] == ["200", "100"]
    assert submitted == [("ws_link", ["200"])]





