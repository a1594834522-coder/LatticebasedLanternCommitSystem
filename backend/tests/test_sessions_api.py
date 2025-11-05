from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import proof as proof_module
from backend.services.proof import ProofEngine


class FakeProofEngine(ProofEngine):
    def __init__(self) -> None:
        super().__init__(default_seed=None)

    async def generate(
        self,
        vector: List[int],
        rules_payload: Dict[str, Any],
        *,
        seed: int | None = None,
        prover_id: str | None = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
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


@pytest.fixture()
def client() -> TestClient:
    app = create_app()

    async def override_proof_engine():
        return FakeProofEngine()

    app.dependency_overrides = {}
    app.dependency_overrides[proof_module.get_proof_engine] = override_proof_engine  # type: ignore
    with TestClient(app) as test_client:
        yield test_client


def test_full_session_flow(client: TestClient) -> None:
    headers_verifier = {"X-API-Role": "verifier"}
    headers_prover = {"X-API-Role": "prover"}

    # Create session
    response = client.post(
        "/api/sessions",
        json={"verifier_id": "ver-1", "metadata": {"label": "demo"}},
        headers=headers_verifier,
    )
    assert response.status_code == 201
    session_id = response.json()["session_id"]

    # Submit rules
    rules_payload = {
        "rules": [
            {"id": "sum1", "type": "sum_equals", "value": 1},
        ]
    }
    response = client.post(
        f"/api/sessions/{session_id}/rules",
        json={"rules": rules_payload},
        headers=headers_verifier,
    )
    assert response.status_code == 200

    # Submit vector
    response = client.post(
        f"/api/sessions/{session_id}/vector",
        json={"vector": [1, 0, 0]},
        headers=headers_prover,
    )
    assert response.status_code == 200

    # Consent (will trigger proof generation on the server)
    response = client.post(
        f"/api/sessions/{session_id}/consent",
        json={"decision": "agreed"},
        headers=headers_prover,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

    # Download proof
    response = client.get(f"/api/sessions/{session_id}/proof", headers=headers_verifier)
    assert response.status_code in {200, 404}
    if response.status_code == 200:
        proof = response.json()
        assert "commitment" in proof["package"]
