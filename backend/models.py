"""Domain models for the backend service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(str, Enum):
    """High-level lifecycle state of a session."""

    CREATED = "created"
    RULES_SUBMITTED = "rules_submitted"
    VECTOR_SUBMITTED = "vector_submitted"
    AWAITING_CONSENT = "awaiting_consent"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ConsentDecision(str, Enum):
    """Proof consent status supplied by the prover."""

    UNSET = "unset"
    AGREED = "agreed"
    REJECTED = "rejected"


class EventType(str, Enum):
    """Types of events emitted as the workflow advances."""

    SESSION_CREATED = "session_created"
    RULES_UPDATED = "rules_updated"
    VECTOR_SUBMITTED = "vector_submitted"
    PROOF_PACKAGE_SUBMITTED = "proof_package_submitted"
    CONSENT_UPDATED = "consent_updated"
    PROOF_STARTED = "proof_started"
    PROOF_COMPLETED = "proof_completed"
    PROOF_FAILED = "proof_failed"
    SESSION_REJECTED = "session_rejected"


@dataclass
class SessionEvent:
    """Immutable record of a business event."""

    event_type: EventType
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SessionState:
    """Aggregated information about a session."""

    session_id: str
    status: SessionStatus = SessionStatus.CREATED
    metadata: Dict[str, Any] = field(default_factory=dict)
    rules: Optional[Dict[str, Any]] = None
    vector: Optional[List[int]] = None
    consent: ConsentDecision = ConsentDecision.UNSET
    consent_reason: Optional[str] = None
    proof_package: Optional[Dict[str, Any]] = None
    proof_metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: List[SessionEvent] = field(default_factory=list)

    def touch(self) -> None:
        """Update the modification timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible mapping."""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "metadata": self.metadata,
            "rules": self.rules,
            "vector": self.vector,
            "consent": self.consent.value,
            "consent_reason": self.consent_reason,
            "proof_package": self.proof_package,
            "proof_metadata": self.proof_metadata,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "history": [event.to_dict() for event in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Rehydrate from a mapping produced by :meth:`to_dict`."""
        history: List[SessionEvent] = []
        for event in data.get("history", []):
            name = event.get("event_type")
            try:
                event_type = EventType(name)
            except ValueError:
                # 兼容旧事件类型，直接跳过
                continue
            history.append(
                SessionEvent(
                    event_type=event_type,
                    payload=event.get("payload", {}),
                    timestamp=datetime.fromisoformat(event["timestamp"]),
                )
            )
        status_value = data["status"]
        try:
            status = SessionStatus(status_value)
        except ValueError:
            legacy_map = {
                "package_submitted": SessionStatus.VECTOR_SUBMITTED,
            }
            status = legacy_map.get(status_value, SessionStatus.CREATED)

        return cls(
            session_id=data["session_id"],
            status=status,
            metadata=data.get("metadata", {}),
            rules=data.get("rules"),
            vector=data.get("vector"),
            consent=ConsentDecision(data.get("consent", ConsentDecision.UNSET.value)),
            consent_reason=data.get("consent_reason"),
            proof_package=data.get("proof_package"),
            proof_metadata=data.get("proof_metadata"),
            error_message=data.get("error_message"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            history=history,
        )

    def record_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Append an event to the history and update timestamps."""
        self.history.append(SessionEvent(event_type=event_type, payload=payload))
        self.touch()
