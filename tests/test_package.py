"""针对 lantern_zk.package 高层接口的测试."""

from __future__ import annotations

import pytest

from lantern_zk import (
    ProofStatus,
    Rule,
    RuleSet,
    RuleType,
    coordinate_zero_rule,
    generate_commitment_package,
    set_random_seed,
    sum_equals_rule,
    verify_commitment_package,
)


def build_basic_rules() -> RuleSet:
    rules = RuleSet()
    rules.add_rule(sum_equals_rule("sum1", value=1))
    rules.add_rule(coordinate_zero_rule("zero_c", index=2))
    return rules


def test_generate_and_verify_success() -> None:
    """基本向量在匹配规则时，所有证明应通过."""
    set_random_seed(42)
    vector = [1, 0, 0, 0]
    rules = build_basic_rules()

    package = generate_commitment_package(vector, rules, seed=42)

    assert package.all_proofs_successful()
    assert verify_commitment_package(package, verbose=False)


def test_rule_failure_is_reflected_in_package() -> None:
    """当向量不满足规则时，应生成 VERIFICATION_FAILED 状态."""
    set_random_seed(123)
    vector = [1, 1, 0, 0]  # index=2 不为 0
    rules = build_basic_rules()

    package = generate_commitment_package(vector, rules, seed=123)

    failed = package.get_failed_rules()
    assert failed == ["zero_c"]
    proof = package.get_proof("zero_c")
    assert proof is not None
    assert proof.status == ProofStatus.VERIFICATION_FAILED
    assert not verify_commitment_package(package, verbose=False)


def test_combined_range_and_sum_rules() -> None:
    """all_in_range 与 sum_equals 组合应通过。"""
    set_random_seed(7)
    vector = [1, 2, 3, 4]
    rules = RuleSet()
    rules.add_rule(
        Rule.from_dict(
            {"id": "range_all", "type": RuleType.ALL_IN_RANGE.value, "min": 0, "max": 10}
        )
    )
    rules.add_rule(sum_equals_rule("total", value=10))

    package = generate_commitment_package(vector, rules, seed=7)

    assert package.all_proofs_successful()
    assert verify_commitment_package(package, verbose=False)


def test_weighted_sum_rule() -> None:
    """weighted_sum 规则支持浮点加权。"""
    set_random_seed(11)
    vector = [10, 5, 0]
    rules = RuleSet()
    rules.add_rule(
        Rule.from_dict(
            {
                "id": "weighted",
                "type": RuleType.WEIGHTED_SUM.value,
                "weights": [0.3, 0.5, 1.0],
                "target": 5.5,
            }
        )
    )

    package = generate_commitment_package(vector, rules, seed=11)

    assert package.all_proofs_successful()
    assert verify_commitment_package(package, verbose=False)


def test_all_binary_violation_reports_failure() -> None:
    """all_binary 若出现非二进制值应标记失败。"""
    set_random_seed(5)
    vector = [0, 1, 2]
    rules = RuleSet()
    rules.add_rule(
        Rule.from_dict(
            {"id": "binary", "type": RuleType.ALL_BINARY.value}
        )
    )

    package = generate_commitment_package(vector, rules, seed=5)

    proof = package.get_proof("binary")
    assert proof is not None
    assert proof.status == ProofStatus.VERIFICATION_FAILED
    assert not verify_commitment_package(package, verbose=False)


def test_unsupported_rule_type_reports_error() -> None:
    """尚未实现的规则类型应返回 ERROR 状态."""
    set_random_seed(0)
    vector = [0, 0, 0]
    rules = RuleSet()
    rules.add_rule(
        Rule.from_dict(
            {"id": "hadamard", "type": RuleType.HADAMARD_PRODUCT.value, "other": [1, 1, 1], "target": [1, 1, 1]}
        )
    )

    package = generate_commitment_package(vector, rules, seed=0)

    proof = package.get_proof("hadamard")
    assert proof is not None
    assert proof.status == ProofStatus.ERROR
    assert "Unsupported rule type" in (proof.error_message or "")
