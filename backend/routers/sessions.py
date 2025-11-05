"""Route definitions for session lifecycle management."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from ..dependencies import get_current_role, require_role
from ..events.broker import EventBroker, get_event_broker
from ..schemas import (
    ConsentRequest,
    CreateSessionRequest,
    ExecuteProofRequest,
    ProofResponse,
    SessionResponse,
    SubmitRulesRequest,
    SubmitVectorRequest,
)
from ..services.sessions import SessionService, get_session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    service: SessionService = Depends(get_session_service),
) -> List[SessionResponse]:
    """List all active sessions for collaboration."""
    sessions = await service.list_sessions()
    return [SessionResponse.from_state(session) for session in sessions]


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role("verifier")],
)
async def create_session(
    payload: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Create a new session initiated by the verifier."""
    metadata = dict(payload.metadata)
    if payload.verifier_id:
        metadata.setdefault("verifier_id", payload.verifier_id)
    state = await service.create_session(metadata)
    return SessionResponse.from_state(state)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
    role: Optional[str] = Depends(get_current_role),
) -> SessionResponse:
    """Retrieve the state of a session."""
    state = await service.get_session(str(session_id))
    return SessionResponse.from_state(state)


@router.post(
    "/{session_id}/rules",
    response_model=SessionResponse,
    dependencies=[require_role("verifier")],
)
async def submit_rules(
    session_id: UUID,
    payload: SubmitRulesRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Submit or update rule definitions for a session."""
    state = await service.submit_rules(str(session_id), payload.rules)
    return SessionResponse.from_state(state)


@router.post(
    "/{session_id}/vector",
    response_model=SessionResponse,
    dependencies=[require_role("prover")],
)
async def submit_vector(
    session_id: UUID,
    payload: SubmitVectorRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Submit the prover's vector to the server for proof generation."""
    state = await service.submit_vector(str(session_id), payload.vector)
    return SessionResponse.from_state(state)


@router.post(
    "/{session_id}/consent",
    response_model=SessionResponse,
    dependencies=[require_role("prover")],
)
async def submit_consent(
    session_id: UUID,
    payload: ConsentRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Prover consents (or rejects) executing the proof."""
    state = await service.update_consent(str(session_id), payload.decision, payload.reason)
    return SessionResponse.from_state(state)


@router.post(
    "/{session_id}/execute",
    response_model=SessionResponse,
    dependencies=[require_role("verifier")],
)
async def execute_proof(
    session_id: UUID,
    payload: ExecuteProofRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Manually trigger proof generation."""
    state = await service.execute_proof(str(session_id), seed=payload.seed, force=payload.force)
    return SessionResponse.from_state(state)


@router.get(
    "/{session_id}/proof",
    response_model=ProofResponse,
)
async def download_proof(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> ProofResponse:
    """Download the proof package once available."""
    state = await service.get_session(str(session_id))
    if not state.proof_package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proof not ready")
    return ProofResponse(session_id=session_id, package=state.proof_package, metadata=state.proof_metadata)


@router.get("/{session_id}/events")
async def stream_events(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
    broker: EventBroker = Depends(get_event_broker),
) -> EventSourceResponse:
    """Stream session events using Server-Sent Events."""
    await service.get_session(str(session_id))  # Ensure session exists

    async def event_generator() -> AsyncIterator[Dict[str, str]]:
        async with broker.subscribe(str(session_id)) as queue:
            while True:
                event = await queue.get()
                yield {
                    "event": event["event_type"],
                    "data": json.dumps(event),
                }

    return EventSourceResponse(event_generator())
