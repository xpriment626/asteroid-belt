"""Pydantic response models for FastAPI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class PoolSummary(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int


class PoolDetail(BaseModel):
    address: str
    name: str | None = None
    bin_step: int | None = None
    bars_count: int
    meta: dict[str, Any]


class Bar(BaseModel):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume_x: int
    volume_y: int
