"""Real-time WebSocket EventBus, log streaming handler, and rolling speed tracker."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from fastapi import WebSocket


class SpeedTracker:
    """Rolling-window byte throughput calculator across concurrent downloads."""

    def __init__(self, window_seconds: float = 3.0):
        self.window_seconds = window_seconds
        self._samples: Deque[Tuple[float, int]] = deque()
        self._last_written_by_file: Dict[str, int] = {}

    def record(self, file_key: str, written: int) -> float:
        now = time.monotonic()
        prev = self._last_written_by_file.get(file_key, 0)
        delta = max(0, int(written) - prev)
        self._last_written_by_file[file_key] = max(prev, int(written))
        if delta > 0:
            self._samples.append((now, delta))
        self._prune(now)
        return self.current_speed(now)

    def finish_file(self, file_key: str) -> None:
        self._last_written_by_file.pop(file_key, None)

    def reset(self) -> None:
        self._samples.clear()
        self._last_written_by_file.clear()

    def current_speed(self, now: Optional[float] = None) -> float:
        now = time.monotonic() if now is None else now
        self._prune(now)
        if not self._samples:
            return 0.0
        total_bytes = sum(delta for _, delta in self._samples)
        span = max(0.25, min(self.window_seconds, now - self._samples[0][0] + 0.1))
        return total_bytes / span

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()


class EventBus:
    """Async pub/sub hub pushing live events and logs to connected UI clients."""

    def __init__(self, max_logs: int = 500):
        self._clients: Set[WebSocket] = set()
        self._logs: Deque[Dict[str, Any]] = deque(maxlen=max_logs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_progress_emit: Dict[str, float] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        # Send recent log history immediately on connect
        if self._logs:
            try:
                await ws.send_json({"type": "logs_snapshot", "data": list(self._logs)})
            except Exception:
                self._clients.discard(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(self._logs)

    def clear_logs(self) -> None:
        self._logs.clear()
        self.emit_threadsafe("logs_cleared", {})

    def append_log(self, level: str, logger_name: str, message: str) -> None:
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "logger": logger_name,
            "message": message.rstrip("\r\n"),
        }
        if not entry["message"]:
            return
        self._logs.append(entry)
        self.emit_threadsafe("log", entry)

    def should_emit_progress(self, key: str, min_interval: float = 0.066) -> bool:
        """Throttle high-frequency byte progress updates (~15 fps per key)."""
        now = time.monotonic()
        last = self._last_progress_emit.get(key, 0.0)
        if now - last < min_interval:
            return False
        self._last_progress_emit[key] = now
        return True

    def emit_threadsafe(self, event_type: str, data: Any) -> None:
        payload = {"type": event_type, "ts": time.time(), "data": data}
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            asyncio.create_task(self._broadcast(payload))
        else:
            try:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(self._broadcast(payload)))
            except RuntimeError:
                pass

    async def publish(self, event_type: str, data: Any) -> None:
        await self._broadcast({"type": event_type, "ts": time.time(), "data": data})

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        if not self._clients:
            return
        dead: List[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


class EventBusLogHandler(logging.Handler):
    """Forwards Python logger records to EventBus."""

    def __init__(self, event_bus: EventBus):
        super().__init__(level=logging.INFO)
        self.event_bus = event_bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            name = record.name.replace("dy-downloader.", "")
            self.event_bus.append_log(record.levelname, name, msg)
        except Exception:
            pass
