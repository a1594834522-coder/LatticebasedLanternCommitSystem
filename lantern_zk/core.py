"""Core Lantern primitives re-exported from ``lattice_zk_module``.

The original project groups all SageMath helpers inside
``lattice_zk_module.py``.  To make the tooling easier to import, we
provide thin wrappers here that simply re-export the public objects.  No
functional changes are introduced in this step; it is purely about
creating a structured module boundary that future refactors can target.
"""

from lattice_zk_module import (  # type: ignore
    R,
    R_q,
    X,
    X_q,
    d,
    q,
    decode_message_bits,
    encode_message_bits,
    lantern_decrypt,
    lantern_encrypt,
    lantern_keygen,
    sample_small_poly,
    sample_uniform_poly,
)

__all__ = [
    "R",
    "R_q",
    "X",
    "X_q",
    "d",
    "q",
    "decode_message_bits",
    "encode_message_bits",
    "lantern_decrypt",
    "lantern_encrypt",
    "lantern_keygen",
    "sample_small_poly",
    "sample_uniform_poly",
]
