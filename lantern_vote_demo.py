#!/usr/bin/env python3
"""匿名投票零知识证明示例。

该脚本实现了基于 Pedersen 承诺与 Sigma 协议的简化示例：
- 选票向量 v ∈ {0,1}^4，表示对 a/b/c/d 的投票，可多选或弃票。
- 可根据命令行参数选择要证明的约束：如“总票数 = t”或“未投给候选人 c”。
- 证明过程不会泄露具体投给谁，但公开承诺与证明可由任何人验证。

注意：示例采用 Fiat-Shamir 变换得到的非交互式证明，仅用于演示概念。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# 2048 位安全素数（RFC 3526 group 14）
P = int(
    """
FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E08
8A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD
3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F4
4C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4
B1FE649286651ECE65381FFFFFFFFFFFFFFFF
""".replace("\n", ""),
    16,
)
Q = (P - 1) // 2  # 大素数子群阶

# 生成阶为 Q 的生成元 g 与独立生成元 h（假设对验证者未知离散对数关系）
G = pow(2, 2, P)
if pow(G, Q, P) != 1:
    raise RuntimeError("Generator G not in subgroup of order Q")

H = pow(G, 0x5F3759DF, P)  # 通过固定指数构造独立生成元
if pow(H, Q, P) != 1:
    raise RuntimeError("Generator H not in subgroup of order Q")

G_INV = pow(G, Q - 1, P)  # g^{-1} mod p

CANDIDATES = ("a", "b", "c", "d")


def _hash_to_int(*values: int) -> int:
    digest = hashlib.sha256()
    for v in values:
        digest.update(v.to_bytes((v.bit_length() + 7) // 8 or 1, "big"))
    return int.from_bytes(digest.digest(), "big") % Q


def _rand_scalar() -> int:
    return secrets.randbelow(Q - 1) + 1


def pedersen_commit(value: int, randomness: int) -> int:
    value_mod = value % Q
    return (pow(G, value_mod, P) * pow(H, randomness % Q, P)) % P


@dataclass
class BitProof:
    A0: int
    A1: int
    e0: int
    e1: int
    s0: int
    s1: int

    def as_dict(self) -> Dict[str, int]:
        return asdict(self)


@dataclass
class EqProof:
    A: int
    e: int
    s: int

    def as_dict(self) -> Dict[str, int]:
        return asdict(self)


@dataclass
class VoteProof:
    commitments: List[int]
    bit_proofs: List[BitProof]
    sum_proof: Optional[EqProof]
    sum_target: Optional[int]
    not_c_proof: Optional[EqProof]
    disallow_c: bool

    def to_json(self) -> str:
        payload = {
            "commitments": self.commitments,
            "bit_proofs": [bp.as_dict() for bp in self.bit_proofs],
            "sum_proof": self.sum_proof.as_dict() if self.sum_proof else None,
            "sum_target": self.sum_target,
            "not_c_proof": self.not_c_proof.as_dict() if self.not_c_proof else None,
            "disallow_c": self.disallow_c,
        }
        return json.dumps(payload, indent=2)


def parse_vote_selection(selection: str) -> Tuple[int, int, int, int]:
    normalized_input = selection.replace(",", " ")
    tokens = [token.strip().lower() for token in normalized_input.split() if token.strip()]

    if not tokens:
        return tuple(0 for _ in CANDIDATES)  # type: ignore[return-value]

    normalized: List[str] = []
    for token in tokens:
        if token in {"none", "abstain", "弃票"}:
            if normalized:
                raise ValueError("输入同时包含弃票与候选人，无法解析。")
            return tuple(0 for _ in CANDIDATES)  # type: ignore[return-value]
        if token in CANDIDATES:
            normalized.append(token)
            continue
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(CANDIDATES):
                normalized.append(CANDIDATES[idx - 1])
                continue
        raise ValueError(f"无法识别的候选项: {token!r}")

    if len(set(normalized)) != len(normalized):
        raise ValueError("同一候选人被重复选择，请只列一次。")

    vector = tuple(1 if candidate in normalized else 0 for candidate in CANDIDATES)
    return vector  # type: ignore[return-value]


def vector_to_choice(vector: Sequence[int]) -> str:
    if len(vector) != len(CANDIDATES):
        return "?"
    chosen = [name for name, bit in zip(CANDIDATES, vector) if bit]
    if not chosen:
        return "abstain"
    if len(chosen) == 1:
        return chosen[0]
    return ",".join(chosen)


def _prove_bit(commitment: int, value: int, randomness: int) -> BitProof:
    if value not in (0, 1):
        raise ValueError("bit value must be 0 or 1")

    statements = [commitment % P, (commitment * G_INV) % P]

    A = [0, 0]
    e = [0, 0]
    s = [0, 0]

    true_idx = value
    false_idx = 1 - value

    w_true = _rand_scalar()
    A[true_idx] = pow(H, w_true, P)

    e[false_idx] = secrets.randbelow(Q)
    s[false_idx] = _rand_scalar()
    A[false_idx] = (
        pow(H, s[false_idx], P) * pow(statements[false_idx], Q - e[false_idx], P)
    ) % P

    chal = _hash_to_int(commitment, A[0], A[1])
    e[true_idx] = (chal - e[false_idx]) % Q
    s[true_idx] = (w_true + e[true_idx] * (randomness % Q)) % Q

    return BitProof(A0=A[0], A1=A[1], e0=e[0], e1=e[1], s0=s[0], s1=s[1])


def _verify_bit(commitment: int, proof: BitProof) -> bool:
    statements = [commitment % P, (commitment * G_INV) % P]

    chal = _hash_to_int(commitment, proof.A0, proof.A1)
    if (proof.e0 + proof.e1) % Q != chal:
        return False

    lhs0 = pow(H, proof.s0, P)
    rhs0 = (proof.A0 * pow(statements[0], proof.e0, P)) % P
    lhs1 = pow(H, proof.s1, P)
    rhs1 = (proof.A1 * pow(statements[1], proof.e1, P)) % P

    return lhs0 == rhs0 and lhs1 == rhs1


def _prove_value_equals(commitment: int, target: int, randomness: int) -> EqProof:
    adjusted = (commitment * pow(G, (Q - target) % Q, P)) % P
    w = _rand_scalar()
    A = pow(H, w, P)
    chal = _hash_to_int(adjusted, A)
    s = (w + chal * (randomness % Q)) % Q
    return EqProof(A=A, e=chal, s=s)


def _verify_value_equals(commitment: int, target: int, proof: EqProof) -> bool:
    adjusted = (commitment * pow(G, (Q - target) % Q, P)) % P
    lhs = pow(H, proof.s, P)
    rhs = (proof.A * pow(adjusted, proof.e, P)) % P
    return lhs == rhs and proof.e == _hash_to_int(adjusted, proof.A)


def prove_vote(
    vote_bits: Sequence[int],
    *,
    sum_target: Optional[int],
    disallow_c: bool,
) -> Tuple[List[int], VoteProof]:
    if len(vote_bits) != 4:
        raise ValueError("需要 4 维投票向量")
    if any(bit not in (0, 1) for bit in vote_bits):
        raise ValueError("投票必须是 0/1 向量")

    randomness = [_rand_scalar() for _ in vote_bits]
    commitments = [pedersen_commit(bit, rnd) for bit, rnd in zip(vote_bits, randomness)]

    bit_proofs = [
        _prove_bit(commitment, bit, rnd)
        for commitment, bit, rnd in zip(commitments, vote_bits, randomness)
    ]

    # 约束：候选人 c（下标 2）不被投票
    not_c_proof: Optional[EqProof] = None
    if disallow_c:
        not_c_proof = _prove_value_equals(commitments[2], 0, randomness[2])

    # 约束：投票总和等于给定目标值
    sum_proof: Optional[EqProof] = None
    if sum_target is not None:
        if not (0 <= sum_target <= len(vote_bits)):
            raise ValueError("sum_target 超出可行范围")
        total_commit = 1
        total_random = 0
        for commitment, rnd in zip(commitments, randomness):
            total_commit = (total_commit * commitment) % P
            total_random = (total_random + rnd) % Q
        sum_proof = _prove_value_equals(total_commit, sum_target, total_random)

    proof = VoteProof(
        commitments=commitments,
        bit_proofs=bit_proofs,
        sum_proof=sum_proof,
        sum_target=sum_target,
        not_c_proof=not_c_proof,
        disallow_c=disallow_c,
    )
    return randomness, proof


def verify_vote_proof(proof: VoteProof) -> bool:
    if len(proof.commitments) != 4 or len(proof.bit_proofs) != 4:
        return False

    # 每个分量证明其为比特
    for commitment, bit_proof in zip(proof.commitments, proof.bit_proofs):
        if not _verify_bit(commitment, bit_proof):
            return False

    # 验证候选人 c 未被投票
    if proof.disallow_c:
        if proof.not_c_proof is None:
            return False
        if not _verify_value_equals(proof.commitments[2], 0, proof.not_c_proof):
            return False
    else:
        if proof.not_c_proof is not None:
            return False

    # 验证投票总和
    if proof.sum_target is not None:
        if proof.sum_proof is None:
            return False
        total_commit = 1
        for commitment in proof.commitments:
            total_commit = (total_commit * commitment) % P
        if not _verify_value_equals(total_commit, proof.sum_target, proof.sum_proof):
            return False
    else:
        if proof.sum_proof is not None:
            return False

    return True


def run_vote(
    vote_bits: Sequence[int],
    *,
    sum_target: Optional[int],
    disallow_c: bool,
    show_randomness: bool,
    json_path: Path | None,
) -> None:
    choice = vector_to_choice(vote_bits)
    print("=== 匿名投票零知识演示 ===")
    print(f"候选人顺序: {', '.join(f'{i+1}:{name}' for i, name in enumerate(CANDIDATES))}")
    print(f"秘密投票向量: {vote_bits} (选中: {choice})")

    randomness, proof = prove_vote(vote_bits, sum_target=sum_target, disallow_c=disallow_c)
    valid = verify_vote_proof(proof)

    print("承诺: ")
    for idx, commitment in enumerate(proof.commitments):
        print(f"  C{idx} = {commitment}")
    if sum_target is not None:
        print(f"证明约束: 总票数 = {sum_target}")
    if disallow_c:
        print("证明约束: 未投给候选人 c")
    print(f"证明通过: {valid}")

    json_payload = proof.to_json()
    if json_path:
        json_path.write_text(json_payload, encoding="utf-8")
        print(f"已写入证明到 {json_path}")
    else:
        print("证明 JSON 摘要:\n", json_payload)

    if show_randomness:
        print("(调试) 承诺随机数:", randomness)


def main() -> None:
    parser = argparse.ArgumentParser(description="匿名投票零知识证明示例")
    parser.add_argument(
        "--select",
        "-s",
        type=str,
        help="指定投票候选人，可用字母(a/b/c/d)或序号(1-4)，多个输入以逗号或空格分隔",
    )
    parser.add_argument(
        "--sum-target",
        type=int,
        default=None,
        help="证明投票总数等于该值（如 1 表示恰好一票，0 表示弃票）。"
    )
    parser.add_argument(
        "--prove-not-c",
        action="store_true",
        help="附加证明：未投给候选人 c",
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        help="将证明保存为 JSON 文件路径",
    )
    parser.add_argument(
        "--show-randomness",
        action="store_true",
        help="输出承诺时使用的随机数，仅用于调试",
    )
    args = parser.parse_args()

    if args.select:
        try:
            vote_bits = parse_vote_selection(args.select)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        prompt = (
            "请输入要投票的候选人（可用字母 a/b/c/d 或序号 1-4，"
            "可多选并以空格/逗号分隔；直接回车表示弃票）: "
        )
        user_input = input(prompt)
        try:
            vote_bits = parse_vote_selection(user_input)
        except ValueError as exc:
            parser.error(str(exc))
            return

    if args.sum_target is not None and not (0 <= args.sum_target <= len(CANDIDATES)):
        parser.error(f"--sum-target 需位于 0~{len(CANDIDATES)} 之间")

    run_vote(
        vote_bits,
        sum_target=args.sum_target,
        disallow_c=args.prove_not_c,
        show_randomness=args.show_randomness,
        json_path=args.export_json,
    )


if __name__ == "__main__":
    main()
