"""Proof generation helpers integrating with lantern_zk."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends

from ..config import Settings, get_settings


class ProofEngine:
    """Wrapper around the Lantern proof generation functions."""

    def __init__(self, default_seed: Optional[int] = None) -> None:
        self._default_seed = default_seed

    async def generate(
        self,
        vector: List[int],
        rules_payload: Dict[str, Any],
        *,
        seed: Optional[int] = None,
        prover_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generate a proof package on the server and return package + metadata."""
        from lantern_zk import RuleSet, generate_commitment_package, verify_commitment_package  # type: ignore

        chosen_seed = seed if seed is not None else self._default_seed

        def _job() -> Tuple[Dict[str, Any], Dict[str, Any]]:
            rules = RuleSet.from_dict(rules_payload)
            package = generate_commitment_package(vector, rules, seed=chosen_seed, prover_id=prover_id)
            verification_result = verify_commitment_package(package, verbose=False)
            return package.to_dict(), {
                "verified": verification_result,
                "seed": chosen_seed,
                "rule_ids": [rule.rule_id for rule in rules.rules],
                "vector_length": len(vector),
            }

        return await asyncio.to_thread(_job)

    async def verify(
        self,
        package_payload: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Verify a proof package and return normalized package data with metadata."""
        from lantern_zk import verify_commitment_package  # type: ignore
        from lantern_zk.package import LanternCommitmentPackage  # type: ignore

        def _job() -> Tuple[Dict[str, Any], Dict[str, Any]]:
            package = LanternCommitmentPackage.from_dict(package_payload)
            verified = verify_commitment_package(package, verbose=False)
            metadata: Dict[str, Any] = {
                "verified": verified,
                "rule_ids": [rule.rule_id for rule in package.rules.rules],
                "vector_length": package.vector_length,
                "proof_count": len(package.proofs),
                "package_metadata": package.metadata,
            }
            return package.to_dict(), metadata

        return await asyncio.to_thread(_job)


_engine: Optional[ProofEngine] = None


def get_proof_engine(settings: Settings = Depends(get_settings)) -> ProofEngine:  # type: ignore[override]
    """Return singleton ProofEngine configured with default settings."""
    global _engine
    if _engine is None:
        _engine = ProofEngine(default_seed=settings.default_seed)
    return _engine
