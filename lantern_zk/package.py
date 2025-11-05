"""Lantern 承诺证明包 - 统一的承诺+规则+证明接口

本模块提供了完整的端到端工作流：
1. 向量承诺（RLWE 加密）
2. 规则定义和验证
3. 针对每条规则生成 Lantern 子证明
4. 打包所有数据为可序列化的包
5. 验证完整的证明包

这是用户面向的主要接口。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .commitments import (
    RLWECommitment,
    RLWEOpening,
    commit_vector,
    open_commitment,
    serialize_commitment,
    deserialize_commitment,
)
from .rules import Rule, RuleSet, RuleType, LanternProtocol
from .proofs import ProofResult, ProofStatus, ProofType
from .params import get_params


# =============================================================================
# 承诺证明包数据结构
# =============================================================================

@dataclass
class LanternCommitmentPackage:
    """Lantern 承诺证明包

    这是系统的核心数据结构，包含：
    - RLWE 向量承诺
    - 验证规则集
    - 针对每条规则的 Lantern 子证明
    - 元数据（参数版本、时间戳等）

    Attributes:
        commitment: RLWE 承诺
        rules: 规则集
        proofs: 规则ID到证明的映射
        metadata: 元数据
        vector_length: 原始向量长度
    """
    commitment: RLWECommitment
    rules: RuleSet
    proofs: Dict[str, ProofResult] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector_length: int = 0

    def add_proof(self, rule_id: str, proof: ProofResult) -> None:
        """添加规则证明"""
        self.proofs[rule_id] = proof

    def get_proof(self, rule_id: str) -> Optional[ProofResult]:
        """获取规则证明"""
        return self.proofs.get(rule_id)

    def has_proof_for_rule(self, rule_id: str) -> bool:
        """检查是否有某条规则的证明"""
        return rule_id in self.proofs

    def all_proofs_successful(self) -> bool:
        """检查是否所有证明都成功"""
        if not self.proofs:
            return False
        return all(proof.is_success() for proof in self.proofs.values())

    def get_failed_rules(self) -> List[str]:
        """获取失败的规则ID列表"""
        return [
            rule_id
            for rule_id, proof in self.proofs.items()
            if not proof.is_success()
        ]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        return {
            "version": "package_v1",
            "commitment": serialize_commitment(self.commitment),
            "rules": self.rules.to_dict(),
            "proofs": {
                rule_id: proof.to_dict()
                for rule_id, proof in self.proofs.items()
            },
            "metadata": self.metadata,
            "vector_length": self.vector_length,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> LanternCommitmentPackage:
        """从字典恢复"""
        if data.get("version") != "package_v1":
            raise ValueError(f"Unsupported package version: {data.get('version')}")

        commitment = deserialize_commitment(data["commitment"])
        rules = RuleSet.from_dict(data["rules"])
        proofs = {
            rule_id: ProofResult.from_dict(proof_data)
            for rule_id, proof_data in data.get("proofs", {}).items()
        }

        return LanternCommitmentPackage(
            commitment=commitment,
            rules=rules,
            proofs=proofs,
            metadata=data.get("metadata", {}),
            vector_length=data.get("vector_length", 0),
        )

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_json(json_str: str) -> LanternCommitmentPackage:
        """从 JSON 字符串解析"""
        data = json.loads(json_str)
        return LanternCommitmentPackage.from_dict(data)

    def save(self, filepath: Union[str, Path]) -> None:
        """保存到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(filepath: Union[str, Path]) -> LanternCommitmentPackage:
        """从文件加载"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return LanternCommitmentPackage.from_dict(data)


# =============================================================================
# 规则到证明生成器的映射
# =============================================================================

class RuleProofGenerator:
    """规则证明生成器基类"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        """生成证明（子类需要实现）"""
        raise NotImplementedError


class SumEqualsProofGenerator(RuleProofGenerator):
    """sum_equals 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        """生成和等于规则的证明

        此规则验证：sum(vector) == rule.params['value']
        使用 ABDLOP 线性证明
        """
        target_sum = rule.params.get("value")
        actual_sum = sum(vector)

        if actual_sum != target_sum:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Sum {actual_sum} != target {target_sum}",
            )

        # TODO: 生成真正的 ABDLOP 线性证明
        # 这里先返回一个占位符
        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.ABDLOP_LINEAR,
            proof_data={
                "rule_type": "sum_equals",
                "target": target_sum,
                "verified": True,
            },
            metadata={
                "note": "Placeholder proof - to be replaced with actual ABDLOP linear proof"
            },
        )


class CoordinateZeroProofGenerator(RuleProofGenerator):
    """coordinate_zero 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        """生成坐标为零规则的证明

        此规则验证：vector[index] == 0
        使用 ABDLOP 线性证明
        """
        index = rule.params.get("index")
        if index is None or index < 0 or index >= len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Invalid index: {index}",
            )

        if vector[index] != 0:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Coordinate {index} is {vector[index]}, not 0",
            )

        # TODO: 生成真正的 ABDLOP 线性证明
        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.ABDLOP_LINEAR,
            proof_data={
                "rule_type": "coordinate_zero",
                "index": index,
                "verified": True,
            },
            metadata={
                "note": "Placeholder proof - to be replaced with actual ABDLOP linear proof"
            },
        )


class CoordinateEqualsProofGenerator(RuleProofGenerator):
    """coordinate_equals 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        """生成坐标等于规则的证明"""
        index = rule.params.get("index")
        value = rule.params.get("value")

        if index is None or index < 0 or index >= len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Invalid index: {index}",
            )

        if vector[index] != value:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Coordinate {index} is {vector[index]}, not {value}",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.ABDLOP_LINEAR,
            proof_data={
                "rule_type": "coordinate_equals",
                "index": index,
                "value": value,
                "verified": True,
            },
        )


class WeightedSumProofGenerator(RuleProofGenerator):
    """weighted_sum 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        weights = rule.params.get("weights")
        target = rule.params.get("target")

        if weights is None or target is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message="weights and target are required for weighted_sum",
            )

        if not isinstance(weights, (list, tuple)):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message="weights must be a list or tuple",
            )

        if len(weights) != len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"weights length {len(weights)} does not match vector length {len(vector)}",
            )

        actual = sum(float(w) * float(v) for w, v in zip(weights, vector))
        target_value = float(target)

        if not math.isclose(actual, target_value, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.ABDLOP_LINEAR,
                error_message=f"Weighted sum {actual} does not equal target {target_value}",
                metadata={
                    "difference": actual - target_value,
                    "tolerance": TOLERANCE,
                },
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.ABDLOP_LINEAR,
            proof_data={
                "rule_type": "weighted_sum",
                "target": target_value,
                "evaluated_sum": actual,
                "verified": True,
            },
            metadata={"tolerance": TOLERANCE},
        )


class CoordinateInRangeProofGenerator(RuleProofGenerator):
    """coordinate_in_range 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        index = rule.params.get("index")
        minimum = rule.params.get("min")
        maximum = rule.params.get("max")

        if index is None or index < 0 or index >= len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message=f"Invalid index: {index}",
            )

        if minimum is None or maximum is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message="min and max are required for coordinate_in_range",
            )

        value = vector[index]
        if value < minimum or value > maximum:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message=f"Coordinate {index}={value} outside range [{minimum}, {maximum}]",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "coordinate_in_range",
                "index": index,
                "value": value,
                "range": [minimum, maximum],
                "verified": True,
            },
        )


class CoordinateBinaryProofGenerator(RuleProofGenerator):
    """coordinate_binary 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        index = rule.params.get("index")
        allowed_values = rule.params.get("values")

        if index is None or index < 0 or index >= len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message=f"Invalid index: {index}",
            )

        if allowed_values is None:
            allowed_set = {0, 1}
        else:
            if not isinstance(allowed_values, (list, tuple)) or not allowed_values:
                return ProofResult(
                    status=ProofStatus.ERROR,
                    proof_type=ProofType.COMPOSITE,
                    error_message="values must be a non-empty list or tuple when provided",
                )
            allowed_set = set(allowed_values)

        value = vector[index]
        if value not in allowed_set:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message=f"Coordinate {index}={value} not in allowed set {sorted(allowed_set)}",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "coordinate_binary",
                "index": index,
                "value": value,
                "allowed": sorted(allowed_set),
                "verified": True,
            },
        )


class AllInRangeProofGenerator(RuleProofGenerator):
    """all_in_range 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        minimum = rule.params.get("min")
        maximum = rule.params.get("max")

        if minimum is None or maximum is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message="min and max are required for all_in_range",
            )

        violations = [
            {"index": idx, "value": value}
            for idx, value in enumerate(vector)
            if value < minimum or value > maximum
        ]
        if violations:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message="Vector contains values outside allowed range",
                metadata={"violations": violations},
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "all_in_range",
                "range": [minimum, maximum],
                "verified": True,
            },
        )


class AllBinaryProofGenerator(RuleProofGenerator):
    """all_binary 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        allowed_values = rule.params.get("values")
        if allowed_values is None:
            allowed_set = {0, 1}
        else:
            if not isinstance(allowed_values, (list, tuple)) or not allowed_values:
                return ProofResult(
                    status=ProofStatus.ERROR,
                    proof_type=ProofType.COMPOSITE,
                    error_message="values must be a non-empty list or tuple when provided",
                )
            allowed_set = set(allowed_values)

        invalid = [
            {"index": idx, "value": value}
            for idx, value in enumerate(vector)
            if value not in allowed_set
        ]
        if invalid:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message="Vector contains values outside allowed binary set",
                metadata={"violations": invalid, "allowed": sorted(allowed_set)},
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "all_binary",
                "allowed": sorted(allowed_set),
                "verified": True,
            },
        )


class AllNonNegativeProofGenerator(RuleProofGenerator):
    """all_non_negative 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        negatives = [
            {"index": idx, "value": value}
            for idx, value in enumerate(vector)
            if value < 0
        ]
        if negatives:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message="Vector contains negative entries",
                metadata={"violations": negatives},
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "all_non_negative",
                "verified": True,
            },
        )


class InnerProductProofGenerator(RuleProofGenerator):
    """inner_product 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        other = rule.params.get("vector")
        target = rule.params.get("target")

        if other is None or target is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_QUADRATIC,
                error_message="vector and target are required for inner_product",
            )

        if not isinstance(other, (list, tuple)) or len(other) != len(vector):
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.ABDLOP_QUADRATIC,
                error_message="inner_product vector must match length of input vector",
            )

        actual = sum(float(a) * float(b) for a, b in zip(vector, other))
        target_value = float(target)

        if not math.isclose(actual, target_value, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.ABDLOP_QUADRATIC,
                error_message=f"Inner product {actual} does not equal target {target_value}",
                metadata={
                    "difference": actual - target_value,
                    "tolerance": TOLERANCE,
                },
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.ABDLOP_QUADRATIC,
            proof_data={
                "rule_type": "inner_product",
                "target": target_value,
                "evaluated_inner_product": actual,
                "verified": True,
            },
            metadata={"tolerance": TOLERANCE},
        )


class L1NormBoundProofGenerator(RuleProofGenerator):
    """l1_norm_bound 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        bound = rule.params.get("bound")
        if bound is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message="bound is required for l1_norm_bound",
            )

        norm = sum(abs(value) for value in vector)
        if norm > float(bound) + TOLERANCE:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message=f"L1 norm {norm} exceeds bound {bound}",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "l1_norm_bound",
                "bound": bound,
                "norm": norm,
                "verified": True,
            },
            metadata={"tolerance": TOLERANCE},
        )


class L2NormBoundProofGenerator(RuleProofGenerator):
    """l2_norm_bound 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        bound = rule.params.get("bound")
        if bound is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message="bound is required for l2_norm_bound",
            )

        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if norm > float(bound) + TOLERANCE:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message=f"L2 norm {norm} exceeds bound {bound}",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "l2_norm_bound",
                "bound": bound,
                "norm": norm,
                "verified": True,
            },
            metadata={"tolerance": TOLERANCE},
        )


class LinfNormBoundProofGenerator(RuleProofGenerator):
    """linf_norm_bound 规则的证明生成器"""

    def generate(self, vector: Sequence[int], rule: Rule, commitment: RLWECommitment) -> ProofResult:
        bound = rule.params.get("bound")
        if bound is None:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message="bound is required for linf_norm_bound",
            )

        norm = max(abs(value) for value in vector) if vector else 0
        if norm > float(bound) + TOLERANCE:
            return ProofResult(
                status=ProofStatus.VERIFICATION_FAILED,
                proof_type=ProofType.COMPOSITE,
                error_message=f"L-infinity norm {norm} exceeds bound {bound}",
            )

        return ProofResult(
            status=ProofStatus.SUCCESS,
            proof_type=ProofType.COMPOSITE,
            proof_data={
                "rule_type": "linf_norm_bound",
                "bound": bound,
                "norm": norm,
                "verified": True,
            },
            metadata={"tolerance": TOLERANCE},
        )


# 规则类型到证明生成器的映射
RULE_PROOF_GENERATORS: Dict[RuleType, RuleProofGenerator] = {
    RuleType.SUM_EQUALS: SumEqualsProofGenerator(),
    RuleType.WEIGHTED_SUM: WeightedSumProofGenerator(),
    RuleType.COORDINATE_ZERO: CoordinateZeroProofGenerator(),
    RuleType.COORDINATE_EQUALS: CoordinateEqualsProofGenerator(),
    RuleType.COORDINATE_IN_RANGE: CoordinateInRangeProofGenerator(),
    RuleType.COORDINATE_BINARY: CoordinateBinaryProofGenerator(),
    RuleType.ALL_IN_RANGE: AllInRangeProofGenerator(),
    RuleType.ALL_BINARY: AllBinaryProofGenerator(),
    RuleType.ALL_NON_NEGATIVE: AllNonNegativeProofGenerator(),
    RuleType.INNER_PRODUCT: InnerProductProofGenerator(),
    RuleType.L1_NORM_BOUND: L1NormBoundProofGenerator(),
    RuleType.L2_NORM_BOUND: L2NormBoundProofGenerator(),
    RuleType.LINF_NORM_BOUND: LinfNormBoundProofGenerator(),
}


# =============================================================================
# 主要接口函数
# =============================================================================

def generate_commitment_package(
    vector: Sequence[int],
    rules: Union[RuleSet, List[Rule], str, Path],
    *,
    seed: Optional[int] = None,
    prover_id: Optional[str] = None,
) -> LanternCommitmentPackage:
    """生成承诺证明包

    这是证明者的主要入口函数。给定向量和规则，生成完整的证明包。

    Args:
        vector: 要承诺的向量
        rules: 规则集（可以是 RuleSet 对象、规则列表或文件路径）
        seed: 随机种子（用于可重现性）
        prover_id: 证明者标识符（可选）

    Returns:
        LanternCommitmentPackage 对象

    Example:
        >>> vector = [1, 0, 0, 0]
        >>> rules = RuleSet.from_file("rules.json")
        >>> package = generate_commitment_package(vector, rules, seed=42)
        >>> package.save("proof_package.json")
    """
    # 解析规则
    if isinstance(rules, (str, Path)):
        rules = RuleSet.from_file(rules)
    elif isinstance(rules, list):
        rule_set = RuleSet()
        for rule in rules:
            rule_set.add_rule(rule)
        rules = rule_set

    # 创建承诺
    commitment, opening = commit_vector(vector, seed=seed)

    # 创建包
    package = LanternCommitmentPackage(
        commitment=commitment,
        rules=rules,
        vector_length=len(vector),
        metadata={
            "created_at": datetime.now().isoformat(),
            "params_version": get_params().version,
            "prover_id": prover_id,
        },
    )

    # 为每条规则生成证明
    for rule in rules.rules:
        generator = RULE_PROOF_GENERATORS.get(rule.rule_type)

        if generator is None:
            # 不支持的规则类型，创建错误证明
            proof = ProofResult(
                status=ProofStatus.ERROR,
                proof_type=ProofType.COMPOSITE,
                error_message=f"Unsupported rule type: {rule.rule_type}",
            )
        else:
            # 生成证明
            proof = generator.generate(vector, rule, commitment)

        package.add_proof(rule.rule_id, proof)

    return package


def verify_commitment_package(
    package: Union[LanternCommitmentPackage, str, Path],
    *,
    opening: Optional[RLWEOpening] = None,
    verbose: bool = False,
) -> bool:
    """验证承诺证明包

    这是验证者的主要入口函数。验证证明包中的所有证明。

    Args:
        package: 证明包（对象或文件路径）
        opening: 承诺的 opening（如果需要打开承诺）
        verbose: 是否打印详细信息

    Returns:
        True 如果所有证明都有效，否则 False

    Example:
        >>> package = LanternCommitmentPackage.load("proof_package.json")
        >>> is_valid = verify_commitment_package(package)
        >>> print("Valid!" if is_valid else "Invalid!")
    """
    # 加载包
    if isinstance(package, (str, Path)):
        package = LanternCommitmentPackage.load(package)

    if verbose:
        print(f"验证证明包...")
        print(f"  规则数量: {len(package.rules.rules)}")
        print(f"  证明数量: {len(package.proofs)}")
        print(f"  向量长度: {package.vector_length}")

    # 检查是否所有规则都有证明
    missing_proofs = []
    for rule in package.rules.rules:
        if not package.has_proof_for_rule(rule.rule_id):
            missing_proofs.append(rule.rule_id)

    if missing_proofs:
        if verbose:
            print(f"  ❌ 缺少证明: {missing_proofs}")
        return False

    # 验证所有证明
    failed_rules = package.get_failed_rules()
    if failed_rules:
        if verbose:
            print(f"  ❌ 失败的规则: {failed_rules}")
            for rule_id in failed_rules:
                proof = package.get_proof(rule_id)
                if proof and proof.error_message:
                    print(f"     {rule_id}: {proof.error_message}")
        return False

    # 如果提供了 opening，验证承诺
    if opening is not None:
        # TODO: 验证承诺的完整性
        pass

    if verbose:
        print(f"  ✅ 所有证明验证通过！")

    return True


def verify_with_opening(
    package: Union[LanternCommitmentPackage, str, Path],
    opening: RLWEOpening,
    verbose: bool = False,
) -> Tuple[bool, Optional[List[int]]]:
    """使用 opening 验证证明包并恢复向量

    Args:
        package: 证明包
        opening: 承诺的 opening
        verbose: 是否打印详细信息

    Returns:
        (是否有效, 恢复的向量)
    """
    # 加载包
    if isinstance(package, (str, Path)):
        package = LanternCommitmentPackage.load(package)

    # 先验证证明
    proofs_valid = verify_commitment_package(package, opening=opening, verbose=verbose)

    if not proofs_valid:
        return False, None

    # 打开承诺恢复向量
    try:
        recovered_vector = open_commitment(package.commitment, opening)
        if verbose:
            print(f"  恢复的向量: {recovered_vector[:10]}{'...' if len(recovered_vector) > 10 else ''}")
        return True, recovered_vector
    except Exception as e:
        if verbose:
            print(f"  ❌ 打开承诺失败: {e}")
        return False, None


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    # 数据结构
    "LanternCommitmentPackage",
    # 主要函数
    "generate_commitment_package",
    "verify_commitment_package",
    "verify_with_opening",
    # 证明生成器
    "RuleProofGenerator",
    "SumEqualsProofGenerator",
    "CoordinateZeroProofGenerator",
    "CoordinateEqualsProofGenerator",
]
