"""Lantern 规则 DSL - 定义和解析验证规则

本模块提供了一个灵活的规则系统，用于表达对向量的各种约束：
- 线性约束（和、加权和等）
- 坐标约束（特定位置的值限制）
- 范数约束（L1, L2, L∞范数）
- 范围约束（向量元素的取值范围）

每个规则类型对应一个 Lantern 子协议（ABDLOP 线性证明、MLWE 等）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union


# =============================================================================
# 规则类型枚举
# =============================================================================

class RuleType(str, Enum):
    """支持的规则类型

    每种规则类型对应特定的 Lantern 子协议
    """
    # === 线性约束 ===
    SUM_EQUALS = "sum_equals"  # 向量元素之和等于某值 (ABDLOP 线性)
    WEIGHTED_SUM = "weighted_sum"  # 加权和约束 (ABDLOP 线性)
    LINEAR_COMBINATION = "linear_combination"  # 通用线性组合 (ABDLOP 线性)

    # === 坐标约束 ===
    COORDINATE_ZERO = "coordinate_zero"  # 特定坐标为 0
    COORDINATE_EQUALS = "coordinate_equals"  # 特定坐标等于某值
    COORDINATE_IN_RANGE = "coordinate_in_range"  # 特定坐标在范围内
    COORDINATE_BINARY = "coordinate_binary"  # 特定坐标是二进制 (0 或 1)

    # === 范数约束 ===
    L1_NORM_BOUND = "l1_norm_bound"  # L1 范数界限
    L2_NORM_BOUND = "l2_norm_bound"  # L2 范数界限（欧几里得范数）
    LINF_NORM_BOUND = "linf_norm_bound"  # L∞ 范数界限（最大绝对值）

    # === 范围约束 ===
    ALL_IN_RANGE = "all_in_range"  # 所有元素在指定范围内
    ALL_BINARY = "all_binary"  # 所有元素都是二进制
    ALL_NON_NEGATIVE = "all_non_negative"  # 所有元素非负

    # === 关系约束 ===
    INNER_PRODUCT = "inner_product"  # 与给定向量的内积 (ABDLOP 二次)
    HADAMARD_PRODUCT = "hadamard_product"  # 逐元素乘积约束

    @classmethod
    def from_string(cls, s: str) -> RuleType:
        """从字符串创建规则类型（不区分大小写）"""
        s_lower = s.lower().replace("-", "_")
        try:
            return cls(s_lower)
        except ValueError:
            raise ValueError(f"Unknown rule type: {s}. Valid types: {list(cls)}")


# =============================================================================
# Lantern 子协议映射
# =============================================================================

class LanternProtocol(str, Enum):
    """Lantern 子证明协议类型"""
    ABDLOP_LINEAR = "abdlop_linear"  # 线性关系证明
    ABDLOP_QUADRATIC = "abdlop_quadratic"  # 二次关系证明
    MLWE = "mlwe"  # MLWE 秘密证明
    RANGE_PROOF = "range_proof"  # 范围证明（组合多个子证明）
    NORM_PROOF = "norm_proof"  # 范数证明


# 规则类型到协议的映射
RULE_TO_PROTOCOL: Dict[RuleType, LanternProtocol] = {
    # 线性约束 -> ABDLOP 线性
    RuleType.SUM_EQUALS: LanternProtocol.ABDLOP_LINEAR,
    RuleType.WEIGHTED_SUM: LanternProtocol.ABDLOP_LINEAR,
    RuleType.LINEAR_COMBINATION: LanternProtocol.ABDLOP_LINEAR,

    # 坐标约束 -> 组合证明或范围证明
    RuleType.COORDINATE_ZERO: LanternProtocol.ABDLOP_LINEAR,
    RuleType.COORDINATE_EQUALS: LanternProtocol.ABDLOP_LINEAR,
    RuleType.COORDINATE_IN_RANGE: LanternProtocol.RANGE_PROOF,
    RuleType.COORDINATE_BINARY: LanternProtocol.RANGE_PROOF,

    # 范数约束 -> 范数证明
    RuleType.L1_NORM_BOUND: LanternProtocol.NORM_PROOF,
    RuleType.L2_NORM_BOUND: LanternProtocol.NORM_PROOF,
    RuleType.LINF_NORM_BOUND: LanternProtocol.NORM_PROOF,

    # 范围约束 -> 范围证明
    RuleType.ALL_IN_RANGE: LanternProtocol.RANGE_PROOF,
    RuleType.ALL_BINARY: LanternProtocol.RANGE_PROOF,
    RuleType.ALL_NON_NEGATIVE: LanternProtocol.RANGE_PROOF,

    # 关系约束 -> 二次证明
    RuleType.INNER_PRODUCT: LanternProtocol.ABDLOP_QUADRATIC,
    RuleType.HADAMARD_PRODUCT: LanternProtocol.ABDLOP_QUADRATIC,
}


# =============================================================================
# 规则数据结构
# =============================================================================

@dataclass
class Rule:
    """单个验证规则

    Attributes:
        rule_id: 规则唯一标识符
        rule_type: 规则类型
        params: 规则参数（键值对）
        description: 规则描述（可选）
    """
    rule_id: str
    rule_type: RuleType
    params: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None

    def get_protocol(self) -> LanternProtocol:
        """获取此规则对应的 Lantern 子协议"""
        return RULE_TO_PROTOCOL.get(self.rule_type, LanternProtocol.ABDLOP_LINEAR)

    def validate_params(self) -> None:
        """验证规则参数的完整性

        Raises:
            ValueError: 如果缺少必需参数或参数无效
        """
        rule_type = self.rule_type

        # 不同规则类型的必需参数
        if rule_type == RuleType.SUM_EQUALS:
            if "value" not in self.params:
                raise ValueError(f"Rule {self.rule_id}: 'sum_equals' requires 'value' parameter")

        elif rule_type == RuleType.WEIGHTED_SUM:
            if "weights" not in self.params or "target" not in self.params:
                raise ValueError(f"Rule {self.rule_id}: 'weighted_sum' requires 'weights' and 'target'")

        elif rule_type == RuleType.COORDINATE_ZERO:
            if "index" not in self.params:
                raise ValueError(f"Rule {self.rule_id}: 'coordinate_zero' requires 'index'")

        elif rule_type == RuleType.COORDINATE_EQUALS:
            if "index" not in self.params or "value" not in self.params:
                raise ValueError(f"Rule {self.rule_id}: 'coordinate_equals' requires 'index' and 'value'")

        elif rule_type in [RuleType.L1_NORM_BOUND, RuleType.L2_NORM_BOUND, RuleType.LINF_NORM_BOUND]:
            if "bound" not in self.params:
                raise ValueError(f"Rule {self.rule_id}: norm rules require 'bound' parameter")

        # 更多验证可以在这里添加

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Rule:
        """从字典创建规则对象

        Args:
            data: 包含规则数据的字典

        Returns:
            Rule 对象

        Raises:
            ValueError: 如果数据格式错误
        """
        # 提取规则 ID（兼容多种格式）
        rule_id = data.get("id") or data.get("rule_id")
        if not rule_id:
            raise ValueError("Rule must have 'id' or 'rule_id' field")

        # 提取规则类型
        rule_type_str = data.get("type") or data.get("rule_type")
        if not rule_type_str:
            raise ValueError(f"Rule {rule_id} must have 'type' or 'rule_type' field")

        try:
            rule_type = RuleType.from_string(str(rule_type_str))
        except ValueError as e:
            raise ValueError(f"Rule {rule_id}: {e}")

        # 提取参数（支持多种格式）
        params = dict(data.get("params", {}))

        # 兼容顶层便捷键
        for key in ["value", "index", "target", "bound", "min", "max"]:
            if key in data and key not in params:
                params[key] = data[key]

        # 特殊处理列表参数
        if "indices" in data:
            params["indices"] = data["indices"]
        if "weights" in data:
            params["weights"] = data["weights"]

        # 提取描述
        description = data.get("description")

        rule = Rule(
            rule_id=str(rule_id),
            rule_type=rule_type,
            params=params,
            description=description,
        )

        # 验证参数
        rule.validate_params()

        return rule

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        result = {
            "id": self.rule_id,
            "type": self.rule_type.value,
            "params": self.params,
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class RuleSet:
    """规则集合

    Attributes:
        rules: 规则列表
        metadata: 元数据（版本、创建时间等）
    """
    rules: List[Rule] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_rule(self, rule: Rule) -> None:
        """添加规则到集合"""
        # 检查是否有重复的规则 ID
        if any(r.rule_id == rule.rule_id for r in self.rules):
            raise ValueError(f"Rule with id '{rule.rule_id}' already exists")
        self.rules.append(rule)

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """根据 ID 获取规则"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def remove_rule(self, rule_id: str) -> bool:
        """移除规则（返回是否成功）"""
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                self.rules.pop(i)
                return True
        return False

    def validate_all(self) -> None:
        """验证所有规则的参数"""
        for rule in self.rules:
            rule.validate_params()

    def get_protocols_required(self) -> List[LanternProtocol]:
        """获取所有规则需要的协议列表（去重）"""
        protocols = [rule.get_protocol() for rule in self.rules]
        return list(set(protocols))

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> RuleSet:
        """从字典创建规则集

        Args:
            data: 包含规则集数据的字典

        Returns:
            RuleSet 对象
        """
        rules_data = data.get("rules", [])
        rules = [Rule.from_dict(r) for r in rules_data]

        metadata = data.get("metadata", {})

        return RuleSet(rules=rules, metadata=metadata)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "rules": [rule.to_dict() for rule in self.rules],
            "metadata": self.metadata,
        }

    @staticmethod
    def from_json(json_str: str) -> RuleSet:
        """从 JSON 字符串解析规则集"""
        data = json.loads(json_str)
        return RuleSet.from_dict(data)

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_file(filepath: Union[str, Path]) -> RuleSet:
        """从文件加载规则集"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return RuleSet.from_dict(data)

    def to_file(self, filepath: Union[str, Path], indent: int = 2) -> None:
        """保存规则集到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)


# =============================================================================
# 便捷创建函数
# =============================================================================

def sum_equals_rule(rule_id: str, value: int, description: Optional[str] = None) -> Rule:
    """创建"和等于"规则"""
    return Rule(
        rule_id=rule_id,
        rule_type=RuleType.SUM_EQUALS,
        params={"value": value},
        description=description or f"向量元素之和必须等于 {value}",
    )


def coordinate_zero_rule(rule_id: str, index: int, description: Optional[str] = None) -> Rule:
    """创建"坐标为零"规则"""
    return Rule(
        rule_id=rule_id,
        rule_type=RuleType.COORDINATE_ZERO,
        params={"index": index},
        description=description or f"坐标 {index} 必须为 0",
    )


def coordinate_equals_rule(
    rule_id: str, index: int, value: int, description: Optional[str] = None
) -> Rule:
    """创建"坐标等于"规则"""
    return Rule(
        rule_id=rule_id,
        rule_type=RuleType.COORDINATE_EQUALS,
        params={"index": index, "value": value},
        description=description or f"坐标 {index} 必须等于 {value}",
    )


def l2_norm_bound_rule(rule_id: str, bound: float, description: Optional[str] = None) -> Rule:
    """创建"L2 范数界限"规则"""
    return Rule(
        rule_id=rule_id,
        rule_type=RuleType.L2_NORM_BOUND,
        params={"bound": bound},
        description=description or f"向量的 L2 范数必须不超过 {bound}",
    )


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    # 枚举
    "RuleType",
    "LanternProtocol",
    # 数据结构
    "Rule",
    "RuleSet",
    # 便捷创建函数
    "sum_equals_rule",
    "coordinate_zero_rule",
    "coordinate_equals_rule",
    "l2_norm_bound_rule",
    # 映射
    "RULE_TO_PROTOCOL",
]
