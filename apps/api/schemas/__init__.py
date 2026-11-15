"""Request/response models (the TypeScript client is generated from these via OpenAPI)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = None


class TokenOut(BaseModel):
    token: str
    user: dict[str, Any]


class Onboarding(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data"]
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    gigsim_token: str | None = None
    hourly_floor: float = Field(30, gt=0, le=1000)
    min_project: float = Field(100, gt=0, le=100000)
    weekly_connects_budget: int = Field(80, ge=0, le=1000)
    saved_searches: list[str] = Field(default_factory=lambda: ["python", "dashboard", "react"])


class SettingsIn(BaseModel):
    hourly_floor: float | None = Field(None, gt=0, le=1000)
    min_project: float | None = Field(None, gt=0, le=100000)
    weekly_connects_budget: int | None = Field(None, ge=0, le=1000)
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    strategy: Literal["evidence_first", "question_first"] | None = None
    saved_searches: list[str] | None = None


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(None, max_length=5000)
    edited_answers: list[str] | None = None
    reason: str | None = Field(None, max_length=500)
    chosen_slot: str | None = None


class RegenerateIn(BaseModel):
    paragraph: str = Field(min_length=5, max_length=2000)
    instruction: str = Field("make it more specific to the client", max_length=300)


class UploadIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=50, max_length=20000)
    kind: Literal["case_study", "review"] = "case_study"


class RunOut(BaseModel):
    run_id: str


class Simple(BaseModel):
    ok: bool = True
    detail: Any = None


_ = EmailStr  # email-validator optional; plain str used for portability
