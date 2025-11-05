"""Redis-backed session repository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from redis.asyncio import Redis

from ..models import EventType, SessionEvent, SessionState
from .base import SessionRepository


class RedisSessionRepository(SessionRepository):
    """Persist session state in Redis using JSON blobs."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def _state_key(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def _events_key(session_id: str) -> str:
        return f"session:{session_id}:events"

    async def create(self, state: SessionState) -> SessionState:
        await self._client.set(self._state_key(state.session_id), json.dumps(state.to_dict()))
        await self._persist_events(state.session_id, state.history)
        return state

    async def get(self, session_id: str) -> Optional[SessionState]:
        raw = await self._client.get(self._state_key(session_id))
        if not raw:
            return None
        data = json.loads(raw)
        history = await self.list_events(session_id)
        state = SessionState.from_dict(data)
        state.history = history
        return state

    async def save(self, state: SessionState) -> SessionState:
        await self._client.set(self._state_key(state.session_id), json.dumps(state.to_dict()))
        await self._persist_events(state.session_id, state.history)
        return state

    async def append_event(self, session_id: str, event: SessionEvent) -> None:
        await self._client.rpush(self._events_key(session_id), json.dumps(event.to_dict()))

    async def list_events(self, session_id: str) -> List[SessionEvent]:
        payloads = await self._client.lrange(self._events_key(session_id), 0, -1)
        events: List[SessionEvent] = []
        for payload in payloads or []:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            data = json.loads(payload)
            name = data.get("event_type")
            try:
                event_type = EventType(name)
            except ValueError:
                # 兼容旧事件类型（如 vector_submitted），直接跳过
                continue
            events.append(
                SessionEvent(
                    event_type=event_type,
                    payload=data.get("payload", {}),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                )
            )
        return events

    async def _persist_events(self, session_id: str, events: List[SessionEvent]) -> None:
        key = self._events_key(session_id)
        await self._client.delete(key)
        if events:
            payloads = [json.dumps(event.to_dict()) for event in events]
            await self._client.rpush(key, *payloads)

    async def list(self) -> List[SessionState]:
        """Return all sessions stored in Redis."""
        sessions: List[SessionState] = []
        cursor = 0
        pattern = self._state_key("*")
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys or []:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                # 忽略事件列表键（session:{id}:events）
                if key.endswith(":events"):
                    continue
                parts = key.split(":", 1)
                if len(parts) != 2:
                    continue
                session_id = parts[1]
                state = await self.get(session_id)
                if state:
                    sessions.append(state)
            if cursor == 0:
                break
        return sessions
