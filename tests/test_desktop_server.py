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


