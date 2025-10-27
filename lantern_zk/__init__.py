"""Lantern ZK helper package.

This package re-exports the core utilities that were previously embedded
in ``lattice_zk_module.py`` so that other components can import them via
stable module paths.  The goal of this first refactor step is to make the
Lantern functionality consumable without having to depend on the large
notebook-derived namespace directly.
"""

from .core import (
    R,
    R_q,
    X,
    X_q,
    d,
    q,
    encode_message_bits,
    decode_message_bits,
    lantern_decrypt,
    lantern_encrypt,
    lantern_keygen,
    sample_small_poly,
    sample_uniform_poly,
)
from .commitments import (
    RLWECommitment,
    RLWEOpening,
    commit_vector,
    open_commitment,
    verify_commitment,
)
from .params import (
    LanternParams,
    DEFAULT_PARAMS,
    PARAMS_FAST,
    PARAMS_STANDARD,
    PARAMS_HIGH_SECURITY,
    get_params,
    set_params,
    set_random_seed,
    get_random_seed,
    reset_random_seed,
)
from .rules import (
    Rule,
    RuleSet,
    RuleType,
    LanternProtocol,
    sum_equals_rule,
    coordinate_zero_rule,
    coordinate_equals_rule,
    l2_norm_bound_rule,
)
from .proofs import (
    ProofResult,
    ProofStatus,
    ProofType,
    ABDLOPCommitParams,
    ABDLOPLinearParams,
    abdlop_commit_proof,
    abdlop_linear_proof,
    create_abdlop_commit_params,
    create_abdlop_linear_params,
)
from .package import (
    LanternCommitmentPackage,
    generate_commitment_package,
    verify_commitment_package,
    verify_with_opening,
)

__all__ = [
    # Core primitives
    "R",
    "R_q",
    "X",
    "X_q",
    "d",
    "q",
    "encode_message_bits",
    "decode_message_bits",
    "lantern_decrypt",
    "lantern_encrypt",
    "lantern_keygen",
    "sample_small_poly",
    "sample_uniform_poly",
    # Commitments
    "RLWECommitment",
    "RLWEOpening",
    "commit_vector",
    "open_commitment",
    "verify_commitment",
    # Parameters and random source
    "LanternParams",
    "DEFAULT_PARAMS",
    "PARAMS_FAST",
    "PARAMS_STANDARD",
    "PARAMS_HIGH_SECURITY",
    "get_params",
    "set_params",
    "set_random_seed",
    "get_random_seed",
    "reset_random_seed",
    # Rules DSL
    "Rule",
    "RuleSet",
    "RuleType",
    "LanternProtocol",
    "sum_equals_rule",
    "coordinate_zero_rule",
    "coordinate_equals_rule",
    "l2_norm_bound_rule",
    # Proofs
    "ProofResult",
    "ProofStatus",
    "ProofType",
    "ABDLOPCommitParams",
    "ABDLOPLinearParams",
    "abdlop_commit_proof",
    "abdlop_linear_proof",
    "create_abdlop_commit_params",
    "create_abdlop_linear_params",
    # Package (Main Interface)
    "LanternCommitmentPackage",
    "generate_commitment_package",
    "verify_commitment_package",
    "verify_with_opening",
]
