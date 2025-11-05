"""Session management business logic."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, status

from ..config import Settings, get_settings
from ..dependencies import get_repository
from ..events.broker import EventBroker, get_event_broker
from ..models import (
    ConsentDecision,
    EventType,
    SessionEvent,
    SessionState,
    SessionStatus,
)
from ..repositories.base import SessionRepository
from .proof import ProofEngine, get_proof_engine


class SessionService:
    """High-level workflow for sessions."""

    def __init__(
        self,
        repository: SessionRepository,
        proof_engine: ProofEngine,
        broker: EventBroker,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._proof_engine = proof_engine
        self._broker = broker
        self._settings = settings

    async def list_sessions(self) -> List[SessionState]:
        sessions = await self._repository.list()
        return sorted(sessions, key=lambda item: item.created_at)

    async def create_session(self, metadata: Dict[str, Any]) -> SessionState:
        session_id = str(uuid4())
        state = SessionState(session_id=session_id, metadata=metadata)
        state.record_event(EventType.SESSION_CREATED, {"metadata": metadata})
        await self._repository.create(state)
        await self._broker.publish(session_id, state.history[-1].to_dict())
        return state

    async def get_session(self, session_id: str) -> SessionState:
        state = await self._repository.get(session_id)
        if not state:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return state

    async def submit_rules(self, session_id: str, rules: Dict[str, Any]) -> SessionState:
        state = await self.get_session(session_id)
        state.rules = rules
        state.status = self._determine_status(state)
        state.record_event(EventType.RULES_UPDATED, {"rule_count": len(rules.get("rules", []))})
        await self._repository.save(state)
        await self._broadcast(state)
        return state

    async def submit_vector(self, session_id: str, vector: List[int]) -> SessionState:
        state = await self.get_session(session_id)
        state.vector = vector
        state.status = self._determine_status(state)
        state.record_event(EventType.VECTOR_SUBMITTED, {"length": len(vector)})
        await self._repository.save(state)
        await self._broadcast(state)
        return state

    async def update_consent(
        self,
        session_id: str,
        decision: ConsentDecision,
        reason: Optional[str] = None,
    ) -> SessionState:
        state = await self.get_session(session_id)
        state.consent = decision
        state.consent_reason = reason
        if decision == ConsentDecision.REJECTED:
            state.status = SessionStatus.REJECTED
            state.record_event(EventType.SESSION_REJECTED, {"reason": reason})
            await self._repository.save(state)
            await self._broadcast(state)
            return state

        if state.rules is None or state.vector is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rules and vector must be submitted before consenting",
            )

        state.status = self._determine_status(state)
        state.record_event(EventType.CONSENT_UPDATED, {"decision": decision.value})
        await self._repository.save(state)
        await self._broadcast(state)
        await self.execute_proof(session_id, seed=self._settings.default_seed, force=False)
        return await self.get_session(session_id)

    async def execute_proof(self, session_id: str, *, seed: Optional[int], force: bool) -> SessionState:
        state = await self.get_session(session_id)
        if state.status == SessionStatus.COMPLETED and not force:
            return state
        if state.vector is None or state.rules is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Missing rules or vector")
        state.status = SessionStatus.IN_PROGRESS
        state.record_event(EventType.PROOF_STARTED, {"seed": seed})
        await self._repository.save(state)
        await self._broadcast(state)

        try:
            package, metadata = await self._proof_engine.generate(
                state.vector,
                state.rules,
                seed=seed,
                prover_id=state.metadata.get("prover_id"),
            )
            state.proof_package = package
            state.proof_metadata = metadata
            state.error_message = None
            state.status = SessionStatus.COMPLETED if metadata.get("verified") else SessionStatus.FAILED
            event_type = EventType.PROOF_COMPLETED if metadata.get("verified") else EventType.PROOF_FAILED
            state.record_event(event_type, {"verified": metadata.get("verified")})
        except Exception as exc:
            state.error_message = str(exc)
            state.status = SessionStatus.FAILED
            state.proof_package = None
            state.proof_metadata = None
            state.record_event(EventType.PROOF_FAILED, {"error": str(exc)})
        await self._repository.save(state)
        await self._broadcast(state)
        return state

    async def list_events(self, session_id: str) -> List[SessionEvent]:
        return await self._repository.list_events(session_id)

    def _determine_status(self, state: SessionState) -> SessionStatus:
        if state.rules and state.vector:
            if state.consent == ConsentDecision.AGREED:
                return SessionStatus.READY
            if state.consent == ConsentDecision.REJECTED:
                return SessionStatus.REJECTED
            return SessionStatus.VECTOR_SUBMITTED
        if state.rules:
            if state.consent == ConsentDecision.AGREED:
                return SessionStatus.READY
            if state.consent == ConsentDecision.UNSET:
                return SessionStatus.RULES_SUBMITTED
            return SessionStatus.AWAITING_CONSENT
        if state.vector:
            return SessionStatus.VECTOR_SUBMITTED
        return SessionStatus.CREATED

    async def _broadcast(self, state: SessionState) -> None:
        if not state.history:
            return
        event = state.history[-1]
        await self._broker.publish(state.session_id, event.to_dict())


async def get_session_service(
    repository: SessionRepository = Depends(get_repository),
    proof_engine: ProofEngine = Depends(get_proof_engine),
    broker: EventBroker = Depends(get_event_broker),
    settings: Settings = Depends(get_settings),
) -> SessionService:
    """FastAPI dependency wiring the service."""
    if repository is None:
        raise RuntimeError("Session repository dependency not configured")
    return SessionService(repository, proof_engine, broker, settings)
