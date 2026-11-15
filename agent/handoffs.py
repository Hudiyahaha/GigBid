"""Structured hand-offs between agents (C3). Anything a later step decides on is one of these objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    skill: str = Field(description="Canonical skill or capability the client needs")
    importance: Literal["must", "nice"] = "must"
    query: str = Field("", description="Short search query used to find portfolio evidence for this requirement")


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = ""
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str = ""
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated")
    vague: bool = False

    @property
    def skills(self) -> list[str]:
        return [r.skill for r in self.requirements]


class RiskFlag(BaseModel):
    code: Literal["free_work", "off_platform_contact", "off_platform_payment", "upfront_payment", "credential_request",
                  "crypto_payment", "prompt_injection", "unverified_payment", "no_hire_history", "low_rating",
                  "unrealistic_budget", "other"]
    severity: float = Field(ge=0, le=1)
    evidence: str = Field("", description="Short quote from the post or client record")


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 = safe, 1 = certain scam")
    client_quality: float = Field(0.5, ge=0, le=1)
    scam: bool = False
    flags: list[RiskFlag] = Field(default_factory=list)
    injection_detected: bool = False
    explanation: str = ""


class EvidenceItem(BaseModel):
    item_id: str
    type: str
    title: str = ""
    project: str | None = None
    source: str = ""
    date: str | None = None
    outcome: str | None = None
    snippet: str = ""
    score: float = 0.0


class RequirementMatch(BaseModel):
    requirement: str
    strength: Literal["strong", "partial", "none"] = "none"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)
    fit_score: float = 0.0
    risk_score: float = 0.0
    auto: bool = Field(False, description="True when the autonomy setting skipped it without asking")


class PriceQuote(BaseModel):
    amount: float
    pay_type: Literal["fixed", "hourly"]
    currency: str = "USD"
    market: dict = Field(default_factory=dict)
    floor: float = 0.0
    connects_cost: int = 0
    connects_usd: float = 0.0
    win_probability: float = 0.0
    expected_value_usd: float = 0.0
    worth_it: bool = True
    rationale: str = ""


class ScreeningAnswer(BaseModel):
    question: str
    answer: str


class Claim(BaseModel):
    text: str
    status: Literal["supported", "partial", "unsupported"] = "unsupported"
    evidence_ids: list[str] = Field(default_factory=list)
    action: Literal["kept", "rewritten", "removed"] = "kept"
    rewritten: str | None = None


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    version: int = 1
    strategy: str = "evidence_first"


class Critique(BaseModel):
    passed: bool
    grounding: float = Field(ge=0, le=1)
    personalisation: float = Field(ge=0, le=1)
    length_ok: bool = True
    issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""


class Redaction(BaseModel):
    rule_id: str
    original: str
    replacement: str = ""


class ComplianceVerdict(BaseModel):
    allowed: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    redactions: list[Redaction] = Field(default_factory=list)
    cleaned_text: str = ""
    rules_version: int = 1


class DryRunPreview(BaseModel):
    operation: str
    payload: dict
    connects_cost: int = 0
    connects_balance_after: int | None = None
    target: str = "gigsim"


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    edited_answers: list[str] | None = None
    reason: str | None = None
    user_id: str | None = None


# ---- conversation graph ----
class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(0.5, ge=0, le=1)
    summary: str = ""
    injection_detected: bool = False


class ReplyDraft(BaseModel):
    thread_id: str
    text: str
    slots: list[str] = Field(default_factory=list)
    intent: str = "other"
    notes: list[str] = Field(default_factory=list)
