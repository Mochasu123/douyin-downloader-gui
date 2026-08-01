"""解析历史存储测试：去重、改名视为新记录、上限、删除/清空。"""

import pytest

from storage.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "history.db"))
    await database.initialize()
    yield database
    await database.close()


def _entry(kind="video", content_id="1", name="标题A", created="2026-08-01 10:00:00"):
    return {
        "kind": kind,
        "content_id": content_id,
        "name": name,
        "original_url": "https://www.douyin.com/video/1",
        "resolved_url": "https://www.douyin.com/video/1",
        "author_name": "作者",
        "avatar_url": "",
        "created_at": created,
    }


@pytest.mark.asyncio
async def test_add_parse_history_dedupes_same_content(db):
    assert await db.add_parse_history(_entry()) is True
    # 同一内容同一名称：不重复记录
    assert await db.add_parse_history(_entry()) is False
    rows = await db.list_parse_history()
    assert len(rows) == 1
    assert rows[0]["name"] == "标题A"


@pytest.mark.asyncio
async def test_add_parse_history_title_change_is_new_record(db):
    await db.add_parse_history(_entry())
    changed = _entry(name="标题B", created="2026-08-01 11:00:00")
    assert await db.add_parse_history(changed) is True
    rows = await db.list_parse_history()
    assert len(rows) == 2
    assert [r["name"] for r in rows] == ["标题B", "标题A"]


@pytest.mark.asyncio
async def test_list_parse_history_newest_first_and_kind_filter(db):
    await db.add_parse_history(_entry(created="2026-08-01 09:00:00"))
    await db.add_parse_history(_entry(content_id="2", name="标题B",
                                      created="2026-08-01 12:00:00"))
    await db.add_parse_history(_entry(kind="user", content_id="u1", name="小明",
                                      created="2026-08-01 11:00:00"))
    videos = await db.list_parse_history(kinds=["video"])
    assert len(videos) == 2
    assert videos[0]["created_at"] == "2026-08-01 12:00:00"
    users = await db.list_parse_history(kinds=["user"])
    assert len(users) == 1
    assert users[0]["name"] == "小明"


@pytest.mark.asyncio
async def test_parse_history_per_kind_limit_keeps_newest(db):
    for index in range(5):
        await db.add_parse_history(
            _entry(content_id=str(index), name=f"标题{index}",
                   created=f"2026-08-01 10:0{index}:00"),
            per_kind_limit=3,
        )
    rows = await db.list_parse_history()
    assert len(rows) == 3
    assert [r["name"] for r in rows] == ["标题4", "标题3", "标题2"]


@pytest.mark.asyncio
async def test_delete_and_clear_parse_history(db):
    await db.add_parse_history(_entry(content_id="1"))
    await db.add_parse_history(_entry(content_id="2", name="标题B"))
    rows = await db.list_parse_history()
    assert len(rows) == 2
    assert await db.delete_parse_history([rows[0]["id"]]) == 1
    assert len(await db.list_parse_history()) == 1
    assert await db.clear_parse_history("video") == 1
    assert await db.list_parse_history() == []
