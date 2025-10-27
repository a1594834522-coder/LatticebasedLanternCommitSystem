"""Vector commitment helpers based on Lantern RLWE encryption.

本模块实现了基于 Lantern RLWE 的向量承诺方案：

特性：
1. 自动多项式拆分：当向量编码超过单个多项式容量时，自动切块
2. 版本控制：记录编码方式和参数版本
3. 序列化支持：可导出为 JSON 格式，方便传输和存储
4. 向后兼容：保持与旧代码的接口兼容

承诺方案说明：
- 向量 -> JSON -> UTF-8 字节 -> 比特串
- 比特串切块（每块 ≤ d bits）
- 每块用 RLWE 加密
- 密文集合构成承诺
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import lantern_zk
from lantern_zk.params import get_params, set_random_seed


# =============================================================================
# 向量编码辅助函数
# =============================================================================

def _vector_to_bits(vector: Sequence[int]) -> List[int]:
    """将向量序列化为比特串

    Args:
        vector: 整数向量

    Returns:
        比特列表（每个元素为 0 或 1）

    Note:
        使用 JSON 序列化向量，然后转换为 UTF-8 字节，再转换为比特
    """
    payload = json.dumps(list(map(int, vector)))
    bit_list: List[int] = []
    for byte in payload.encode("utf-8"):
        for i in range(8):
            bit_list.append((byte >> i) & 1)
    return bit_list


def _bits_to_vector(bits: Sequence[int]) -> List[int]:
    """从比特串恢复向量

    Args:
        bits: 比特列表

    Returns:
        恢复的整数向量

    Raises:
        ValueError: 如果比特长度不是 8 的倍数
    """
    if len(bits) % 8 != 0:
        raise ValueError("bit length must be a multiple of 8")
    byte_values: List[int] = []
    for idx in range(0, len(bits), 8):
        value = 0
        for bit in range(8):
            value |= (bits[idx + bit] & 1) << bit
        byte_values.append(value)
    payload = bytes(byte_values).decode("utf-8")
    return [int(x) for x in json.loads(payload)]


def _split_bits_into_chunks(bits: List[int], chunk_size: int) -> List[List[int]]:
    """将比特串切分成多个块

    Args:
        bits: 完整的比特列表
        chunk_size: 每块的最大比特数

    Returns:
        比特块列表
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    chunks = []
    for i in range(0, len(bits), chunk_size):
        chunks.append(bits[i:i + chunk_size])
    return chunks


def _merge_bit_chunks(chunks: List[List[int]]) -> List[int]:
    """合并比特块

    Args:
        chunks: 比特块列表

    Returns:
        完整的比特列表
    """
    result = []
    for chunk in chunks:
        result.extend(chunk)
    return result


# =============================================================================
# Sage 对象序列化辅助函数
# =============================================================================

def _poly_to_coeff_list(poly) -> List[int]:
    """将 Sage 多项式转换为系数列表

    Args:
        poly: Sage 多项式对象

    Returns:
        系数列表（整数）
    """
    try:
        # 尝试获取系数列表
        coeffs = poly.list()
        return [int(c) for c in coeffs]
    except AttributeError:
        # 如果不是多项式，假设是标量
        return [int(poly)]


def _coeff_list_to_poly(coeffs: List[int], ring):
    """从系数列表重建 Sage 多项式

    Args:
        coeffs: 系数列表
        ring: 目标多项式环

    Returns:
        Sage 多项式对象
    """
    return ring(coeffs)


# =============================================================================
# 承诺数据结构
# =============================================================================

@dataclass
class RLWECommitment:
    """RLWE 承诺对象（支持多块）

    Attributes:
        public_key: 公钥元组 (a, b)，可以是 Sage 对象或序列化列表
        ciphertext_chunks: 密文块列表，每块对应一个多项式加密
        chunk_bit_lengths: 每块的比特长度
        total_bits: 总比特数
        encoding_version: 编码版本号
        params_version: 参数集版本号
    """
    public_key: Tuple[Any, Any]
    ciphertext_chunks: List[Tuple[Any, Any]]
    chunk_bit_lengths: List[int]
    total_bits: int
    encoding_version: str = "1.0.0"
    params_version: str = field(default_factory=lambda: get_params().version)

    def num_chunks(self) -> int:
        """返回密文块的数量"""
        return len(self.ciphertext_chunks)


@dataclass
class RLWEOpening:
    """RLWE 承诺的 opening（私钥）

    Attributes:
        secret: 私钥（Sage 多项式对象）
    """
    secret: object


# =============================================================================
# 核心承诺函数（支持多块）
# =============================================================================

def commit_vector(
    vector: Sequence[int],
    *,
    bound: int = 2,
    seed: Optional[int] = None,
    chunk_size: Optional[int] = None,
) -> Tuple[RLWECommitment, RLWEOpening]:
    """创建向量承诺（支持自动多项式拆分）

    Args:
        vector: 要承诺的整数向量
        bound: RLWE 噪声界限（默认 2）
        seed: 随机种子（用于可重现性）
        chunk_size: 每块的最大比特数（默认使用 d）

    Returns:
        (commitment, opening) 元组

    Note:
        如果向量编码后的比特数超过 chunk_size，会自动分成多个块，
        每块独立加密
    """
    # 设置随机种子
    if seed is not None:
        set_random_seed(seed)

    # 确定块大小
    if chunk_size is None:
        chunk_size = lantern_zk.d

    # 将向量转换为比特串
    bits = _vector_to_bits(vector)
    total_bits = len(bits)

    # 切分成多个块
    bit_chunks = _split_bits_into_chunks(bits, chunk_size)

    # 生成密钥对（所有块共享同一密钥对）
    pubkey, secret = lantern_zk.lantern_keygen(bound=bound)

    # 对每个块进行加密
    ciphertext_chunks = []
    chunk_bit_lengths = []

    for chunk in bit_chunks:
        ciphertext = lantern_zk.lantern_encrypt(pubkey, chunk, bound=bound)
        ciphertext_chunks.append(ciphertext)
        chunk_bit_lengths.append(len(chunk))

    # 构建承诺对象
    commitment = RLWECommitment(
        public_key=(pubkey["a"], pubkey["b"]),
        ciphertext_chunks=ciphertext_chunks,
        chunk_bit_lengths=chunk_bit_lengths,
        total_bits=total_bits,
    )
    opening = RLWEOpening(secret=secret)

    return commitment, opening


def open_commitment(commitment: RLWECommitment, opening: RLWEOpening) -> List[int]:
    """打开承诺，恢复原始向量

    Args:
        commitment: RLWE 承诺对象
        opening: 承诺的 opening（私钥）

    Returns:
        恢复的整数向量

    Raises:
        ValueError: 如果解密失败或数据格式错误
    """
    # 解密所有块
    all_bits = []
    for ciphertext, chunk_len in zip(commitment.ciphertext_chunks, commitment.chunk_bit_lengths):
        bits, _ = lantern_zk.lantern_decrypt(opening.secret, ciphertext, chunk_len)
        all_bits.extend(bits[:chunk_len])

    # 验证总比特数
    if len(all_bits) != commitment.total_bits:
        raise ValueError(
            f"Decrypted bits length {len(all_bits)} != expected {commitment.total_bits}"
        )

    # 补齐到 8 的倍数（JSON 解码需要完整字节）
    padding = (8 - len(all_bits) % 8) % 8
    all_bits.extend([0] * padding)

    # 转换回向量
    return _bits_to_vector(all_bits[:commitment.total_bits])


def verify_commitment(
    commitment: RLWECommitment,
    opening: RLWEOpening,
    expected_vector: Sequence[int]
) -> bool:
    """验证承诺是否匹配预期向量

    Args:
        commitment: RLWE 承诺对象
        opening: 承诺的 opening
        expected_vector: 预期的向量

    Returns:
        True 如果验证通过，否则 False
    """
    try:
        recovered = open_commitment(commitment, opening)
        return list(map(int, expected_vector)) == recovered
    except Exception:
        return False


# =============================================================================
# 序列化和反序列化
# =============================================================================

def serialize_commitment(commitment: RLWECommitment) -> Dict[str, Any]:
    """将承诺序列化为 JSON 可存储的字典

    Args:
        commitment: RLWE 承诺对象

    Returns:
        可序列化的字典

    Note:
        Sage 多项式对象会被转换为系数列表
    """
    # 转换公钥
    pubkey_a = _poly_to_coeff_list(commitment.public_key[0])
    pubkey_b = _poly_to_coeff_list(commitment.public_key[1])

    # 转换所有密文块
    serialized_chunks = []
    for ciphertext in commitment.ciphertext_chunks:
        c0 = _poly_to_coeff_list(ciphertext[0])
        c1 = _poly_to_coeff_list(ciphertext[1])
        serialized_chunks.append({"c0": c0, "c1": c1})

    return {
        "version": "commitment_v1",
        "encoding_version": commitment.encoding_version,
        "params_version": commitment.params_version,
        "public_key": {
            "a": pubkey_a,
            "b": pubkey_b,
        },
        "ciphertext_chunks": serialized_chunks,
        "chunk_bit_lengths": commitment.chunk_bit_lengths,
        "total_bits": commitment.total_bits,
    }


def deserialize_commitment(data: Dict[str, Any]) -> RLWECommitment:
    """从序列化的字典恢复承诺对象

    Args:
        data: 序列化的字典

    Returns:
        RLWECommitment 对象

    Raises:
        ValueError: 如果版本不兼容或数据格式错误
    """
    if data.get("version") != "commitment_v1":
        raise ValueError(f"Unsupported commitment version: {data.get('version')}")

    # 恢复公钥
    pubkey_a = _coeff_list_to_poly(data["public_key"]["a"], lantern_zk.R_q)
    pubkey_b = _coeff_list_to_poly(data["public_key"]["b"], lantern_zk.R_q)

    # 恢复所有密文块
    ciphertext_chunks = []
    for chunk_data in data["ciphertext_chunks"]:
        c0 = _coeff_list_to_poly(chunk_data["c0"], lantern_zk.R_q)
        c1 = _coeff_list_to_poly(chunk_data["c1"], lantern_zk.R_q)
        ciphertext_chunks.append((c0, c1))

    return RLWECommitment(
        public_key=(pubkey_a, pubkey_b),
        ciphertext_chunks=ciphertext_chunks,
        chunk_bit_lengths=data["chunk_bit_lengths"],
        total_bits=data["total_bits"],
        encoding_version=data["encoding_version"],
        params_version=data["params_version"],
    )


def save_commitment(commitment: RLWECommitment, filepath: str) -> None:
    """将承诺保存到文件

    Args:
        commitment: RLWE 承诺对象
        filepath: 输出文件路径（JSON 格式）
    """
    data = serialize_commitment(commitment)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


def load_commitment(filepath: str) -> RLWECommitment:
    """从文件加载承诺

    Args:
        filepath: 承诺文件路径（JSON 格式）

    Returns:
        RLWECommitment 对象
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    return deserialize_commitment(data)


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    # 数据结构
    "RLWECommitment",
    "RLWEOpening",
    # 核心函数
    "commit_vector",
    "open_commitment",
    "verify_commitment",
    # 序列化
    "serialize_commitment",
    "deserialize_commitment",
    "save_commitment",
    "load_commitment",
]

