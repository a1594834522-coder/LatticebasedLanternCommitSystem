"""Pydantic schemas for request/response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator

from .models import ConsentDecision, EventType, SessionState, SessionStatus


class CreateSessionRequest(BaseModel):
    """Verifier request to create a new session."""

    verifier_id: Optional[str] = Field(default=None, description="Identifier for the verifier")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """Response payload describing a session."""

    session_id: UUID
    status: SessionStatus
    consent: ConsentDecision
    consent_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    rules_submitted: bool
    vector_submitted: bool
    proof_available: bool
    error_message: Optional[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    rules: Optional[Dict[str, Any]] = None
    proof_metadata: Optional[Dict[str, Any]] = None
    history: List[EventPayload] = Field(default_factory=list)

    @classmethod
    def from_state(cls, state: SessionState, metadata: Optional[Dict[str, Any]] = None) -> "SessionResponse":
        history = [EventPayload.from_event_dict(event.to_dict()) for event in state.history]
        return cls(
            session_id=UUID(state.session_id),
            status=state.status,
            consent=state.consent,
            consent_reason=state.consent_reason,
            created_at=state.created_at,
            updated_at=state.updated_at,
            rules_submitted=state.rules is not None,
            vector_submitted=state.vector is not None,
            proof_available=state.proof_package is not None,
            error_message=state.error_message,
            metadata=metadata or state.metadata,
            rules=state.rules,
            proof_metadata=state.proof_metadata,
            history=history,
        )


class SubmitRulesRequest(BaseModel):
    """Payload containing rule definitions."""

    rules: Dict[str, Any]

    @validator("rules")
    def validate_rules(cls, value):  # type: ignore[override]
        if "rules" not in value:
            raise ValueError("rules payload must contain 'rules' key")
        return value


class SubmitVectorRequest(BaseModel):
    """Prover-submitted vector data."""

    vector: List[int]

    @validator("vector")
    def validate_vector(cls, value):  # type: ignore[override]
        if not value:
            raise ValueError("vector must contain at least one entry")
        if not all(isinstance(v, int) for v in value):
            raise ValueError("vector values must be integers")
        return value


class ConsentRequest(BaseModel):
    """Prover consent to execute a proof."""

    decision: ConsentDecision
    reason: Optional[str] = None

    @validator("decision")
    def ensure_set(cls, value):  # type: ignore[override]
        if value == ConsentDecision.UNSET:
            raise ValueError("decision must be 'agreed' or 'rejected'")
        return value


class ExecuteProofRequest(BaseModel):
    """Optional payload when explicitly triggering proof generation."""

    seed: Optional[int] = Field(default=None, description="Override the RNG seed")
    force: bool = Field(default=False, description="Force execution even if already completed")


class ProofResponse(BaseModel):
    """Encoded proof package data."""

    session_id: UUID
    package: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class EventPayload(BaseModel):
    """Single event representation returned via SSE."""

    event_type: EventType
    payload: Dict[str, Any]
    timestamp: datetime

    @classmethod
    def from_event_dict(cls, data: Dict[str, Any]) -> "EventPayload":
        return cls(
            event_type=EventType(data["event_type"]),
            payload=data.get("payload", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
