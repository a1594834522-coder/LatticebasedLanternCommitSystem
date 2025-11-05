import pytest
from fakeredis.aioredis import FakeRedis

from backend.events.broker import EventBroker
from backend.models import ConsentDecision, EventType
from backend.repositories.redis import RedisSessionRepository
from backend.services.sessions import SessionService
from backend.services.proof import ProofEngine


class StubProofEngine(ProofEngine):
    def __init__(self) -> None:
        super().__init__(default_seed=None)

    async def generate(self, vector, rules_payload, *, seed=None, prover_id=None):  # type: ignore[override]
        package = {
            "commitment": {"vector": vector, "seed": seed},
            "rules": rules_payload,
        }
        metadata = {
            "verified": True,
            "seed": seed,
            "rule_ids": [rule.get("id") for rule in rules_payload.get("rules", [])],
            "vector_length": len(vector),
        }
        return package, metadata


class StubSettings:
    default_seed = 99
    api_tokens = {}


@pytest.mark.asyncio
async def test_service_with_redis_persistence():
    redis = FakeRedis()
    repository = RedisSessionRepository(redis)
    broker = EventBroker()
    proof_engine = StubProofEngine()
    settings = StubSettings()

    service = SessionService(repository, proof_engine, broker, settings)  # type: ignore[arg-type]

    state = await service.create_session({"label": "redis-test"})
    session_id = state.session_id

    rules_payload = {
        "rules": [
            {"id": "sum1", "type": "sum_equals", "value": 1},
        ]
    }

    async with broker.subscribe(session_id) as queue:
        await service.submit_rules(session_id, rules_payload)
        rules_event = await queue.get()
        assert rules_event["event_type"] == EventType.RULES_UPDATED.value

        await service.submit_vector(session_id, [1])
        vector_event = await queue.get()
        assert vector_event["event_type"] == EventType.VECTOR_SUBMITTED.value

        await service.update_consent(session_id, ConsentDecision.AGREED)
        consent_event = await queue.get()
        assert consent_event["event_type"] == EventType.CONSENT_UPDATED.value

        proof_started = await queue.get()
        assert proof_started["event_type"] == EventType.PROOF_STARTED.value

        proof_completed = await queue.get()
        assert proof_completed["event_type"] == EventType.PROOF_COMPLETED.value

    persisted = await repository.get(session_id)
    assert persisted is not None
    assert persisted.proof_package is not None
    assert persisted.status.value == "completed"

    events = await repository.list_events(session_id)
    assert len(events) >= 5
    assert events[-1].event_type == EventType.PROOF_COMPLETED
