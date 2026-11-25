"""Embedded FastAPI + WebSocket backend for the modern desktop GUI."""

from desktop_server.app import create_app

__all__ = ["create_app"]
