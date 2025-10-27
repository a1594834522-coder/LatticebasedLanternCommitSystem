#!/usr/bin/env sage -python
"""Lantern encryption + zero-knowledge proof demo based on 2022-284."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np
import sage.all as sg

from lattice_zk_module import (
    R_q,
    d,
    q,
    Zq_2_ZZ,
    abdlop_mlwe,
    eta_challenge_v2,
    get_challenge_v2,
    k_sigma_n1,
    lantern_decrypt,
    lantern_encrypt,
    lantern_keygen,
    norm_Rql,
    norm_Rql_bound,
    rej1,
    rej1_M,
    rej2,
    rej2_M,
    rej_bimodal,
    rej_bimodal_M,
    stack_vec_Rql,
    zv,
    IM,
    ZM,
    N_2_binary_Rq,
    rand_Rql,
    rand_Rql_bin,
    rand_Rql_small,
    rand_Rq_mat,
)


def message_to_bits(message: str) -> List[int]:
    bit_list: List[int] = []
    for byte in message.encode("utf-8"):
        for i in range(8):
            bit_list.append((byte >> i) & 1)
    return bit_list


def bits_to_message(bits: Sequence[int]) -> str:
    if len(bits) % 8 != 0:
        raise ValueError("bit length must be a multiple of 8")
    bytes_out: List[int] = []
    for idx in range(0, len(bits), 8):
        value = 0
        for bit in range(8):
            value |= (bits[idx + bit] & 1) << bit
        bytes_out.append(value)
    return bytes(bytes_out).decode("utf-8")


def centered_coeffs(poly: sg.Element) -> List[int]:
    return [Zq_2_ZZ(int(coeff)) for coeff in poly.list()]


def infinity_norm(poly: sg.Element) -> int:
    return max(abs(value) for value in centered_coeffs(poly))


@dataclass
class KeyMaterial:
    a: sg.Element
    b: sg.Element
    secret: sg.Element
    error: sg.Element

    def summary(self) -> Dict[str, Any]:
        return {
            "a_coeffs": centered_coeffs(self.a),
            "b_coeffs": centered_coeffs(self.b),
            "secret_coeffs": centered_coeffs(self.secret),
            "error_coeffs": centered_coeffs(self.error),
            "secret_inf_norm": infinity_norm(self.secret),
            "error_inf_norm": infinity_norm(self.error),
        }


@dataclass
class Ciphertext:
    u: sg.Element
    v: sg.Element
    bit_length: int

    def summary(self) -> Dict[str, Any]:
        return {
            "u_coeffs": centered_coeffs(self.u),
            "v_coeffs": centered_coeffs(self.v),
            "bit_length": self.bit_length,
        }


@dataclass
class ProofOutcome:
    accepted: bool
    attempts: int
    settings: Dict[str, Any]
    module_matrix: sg.matrix
    module_vector: sg.vector

    def summary(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "attempts": self.attempts,
            "settings": self.settings,
            "module_matrix_rows": [
                [centered_coeffs(entry) for entry in row]
                for row in self.module_matrix.rows()
            ],
            "module_vector": [centered_coeffs(poly) for poly in self.module_vector],
        }


def seed_entropy(seed: int | None) -> None:
    if seed is None:
        return
    random.seed(seed)
    np.random.seed(seed & 0xFFFFFFFF)
    sg.set_random_seed(seed)


def generate_keys(bound: int) -> KeyMaterial:
    pubkey, secret = lantern_keygen(bound=bound)
    error = pubkey["b"] - pubkey["a"] * secret
    return KeyMaterial(pubkey["a"], pubkey["b"], secret, error)


def encrypt_message(message: str, bound: int, pubkey: Dict[str, sg.Element]) -> Ciphertext:
    bits = message_to_bits(message)
    ciphertext = lantern_encrypt(pubkey, bits, bound=bound)
    return Ciphertext(ciphertext[0], ciphertext[1], len(bits))


def decrypt_ciphertext(ciphertext: Ciphertext, secret: sg.Element) -> str:
    bits, _ = lantern_decrypt(secret, (ciphertext.u, ciphertext.v), ciphertext.bit_length)
    return bits_to_message(bits[: ciphertext.bit_length])


def run_mlwe_proof(
    key: KeyMaterial,
    *,
    max_attempts: int = 32,
    nu_s1: int = 1,
    nu_s2: int = 1,
) -> ProofOutcome:
    m1 = 1
    m2 = 12
    n = 4
    Z = 1
    lambd = 2

    gamma1 = 25
    gamma2 = 3
    gamma3 = 8

    eta = eta_challenge_v2
    k = k_sigma_n1

    alpha_s1 = norm_Rql_bound(m1, nu_s1)
    std1 = gamma1 * eta * sg.sqrt(alpha_s1**2 + d)
    rep_M1 = rej1_M(gamma1)

    alpha_s2 = norm_Rql_bound(m2, nu_s2)
    std2 = gamma2 * eta * alpha_s2
    rep_M2 = rej2_M(gamma2)

    std3 = gamma3 * sg.sqrt(337) * sg.sqrt(d + 2048)
    rep_M3 = rej_bimodal_M(gamma3)
    roh = 1.64

    s1 = sg.vector(R_q, [key.secret])
    A_module = sg.matrix(R_q, [[key.a]])
    u_module = sg.vector(R_q, [key.b])

    attempts = 0
    while attempts < max_attempts:
        attempts += 1

        s2 = rand_Rql_small(m2, nu_s2)
        A1 = rand_Rq_mat(n, m1 + Z)
        A2 = rand_Rq_mat(n, m2)
        B_gamma = rand_Rq_mat(max(1, 256 // d), m2)
        B_beta = rand_Rq_mat(1, m2)
        B_ext = rand_Rq_mat(lambd, m2)
        b_ext = rand_Rql(m2)

        n_is = [m1 + m1]
        E_s_is = [IM(m1).stack(A_module)]
        v_is = [-stack_vec_Rql([zv(m1), u_module])]
        B_is = [sg.sqrt(2048)]

        norms = [norm_Rql(E_s_is[0] * s1 + v_is[0])]
        squared_norm_diffs = [B_is[0] ** 2 - round(norms[0] ** 2)]
        if squared_norm_diffs[0] < 0:
            squared_norm_diffs[0] = 0
        theta = sg.vector(R_q, [N_2_binary_Rq(int(squared_norm_diffs[0]))])

        tA = A1 * stack_vec_Rql([s1, theta]) + A2 * s2

        result = abdlop_mlwe(
            m1,
            m2,
            n,
            k,
            Z,
            n_is,
            lambd,
            False,
            rej1,
            rej2,
            rej_bimodal,
            get_challenge_v2,
            std1,
            rep_M1,
            std2,
            rep_M2,
            std3,
            rep_M3,
            roh,
            s1,
            s2,
            A1,
            A2,
            B_gamma,
            B_beta,
            B_ext,
            b_ext,
            theta,
            tA,
            E_s_is,
            v_is,
            B_is,
        )

        if result != "Rejected" and bool(result):
            return ProofOutcome(
                True,
                attempts,
                {
                    "m1": m1,
                    "m2": m2,
                    "n": n,
                    "lambda": lambd,
                    "gamma1": gamma1,
                    "gamma2": gamma2,
                    "gamma3": gamma3,
                },
                A_module,
                u_module,
            )

    return ProofOutcome(
        False,
        attempts,
        {
            "m1": m1,
            "m2": m2,
            "n": n,
            "lambda": lambd,
            "gamma1": gamma1,
            "gamma2": gamma2,
            "gamma3": gamma3,
        },
        A_module,
        u_module,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lantern RLWE demo with zero-knowledge proof (CRYPTO 2022)."
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="Lantern demo!",
        help="UTF-8 message to encrypt",
    )
    parser.add_argument(
        "--bound",
        type=int,
        default=2,
        help="Coefficient bound for small polynomials",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for Python/Numpy/Sage RNGs",
    )
    parser.add_argument(
        "--proof-max-attempts",
        type=int,
        default=64,
        help="Maximum rejection-sampling attempts for the proof",
    )
    parser.add_argument(
        "--export-json",
        type=str,
        default=None,
        help="Optional path to save a JSON summary",
    )
    args = parser.parse_args()

    seed_entropy(args.seed)

    key_material = generate_keys(args.bound)
    ciphertext = encrypt_message(args.message, args.bound, {"a": key_material.a, "b": key_material.b})
    recovered = decrypt_ciphertext(ciphertext, key_material.secret)
    proof = run_mlwe_proof(key_material, max_attempts=args.proof_max_attempts)

    summary = {
        "parameters": {"d": d, "q": int(q)},
        "message": args.message,
        "recovered_message": recovered,
        "key": key_material.summary(),
        "ciphertext": ciphertext.summary(),
        "proof": proof.summary(),
    }

    print("=== Lantern 应用流程 ===")
    print(f"原始消息: {args.message!r}")
    print(f"解密结果: {recovered!r}")
    print(f"消息往返成功: {recovered == args.message}")
    print("-- 秘钥信息 --")
    print(f"||s||_∞ = {summary['key']['secret_inf_norm']}")
    print(f"||e||_∞ = {summary['key']['error_inf_norm']}")
    print("-- 零知识证明 --")
    print(f"证明是否接受: {summary['proof']['accepted']}")
    print(f"重试次数: {summary['proof']['attempts']}")

    if args.export_json:
        with open(args.export_json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
        print(f"已写入摘要到 {args.export_json}")


if __name__ == "__main__":
    main()
