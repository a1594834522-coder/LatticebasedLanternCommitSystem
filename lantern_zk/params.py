"""Lantern ZK 系统参数与随机源统一管理

本模块封装了所有系统级参数和随机数生成器的统一接口，确保：
1. 参数在整个系统中保持一致
2. 随机源可以通过种子进行控制，保证可重现性
3. 方便后续参数调优和配置管理
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# 尝试导入 SageMath，如果不可用则提供占位符
try:
    import sage.all as sg
    SAGE_AVAILABLE = True
except ImportError:
    sg = None  # type: ignore
    SAGE_AVAILABLE = False


# =============================================================================
# 默认参数集
# =============================================================================

@dataclass(frozen=True)
class LanternParams:
    """Lantern 系统参数集

    Attributes:
        kappa: 安全参数（比特）
        d: 多项式环维度（X^d + 1）
        q: 模数（素数）
        gamma: 拒绝采样参数（控制接受率）
        std_dev: 高斯采样标准差
        max_small_coeff: 小系数的上界（用于 small poly 采样）
        rlwe_bound: RLWE 加密的噪声界限
        version: 参数集版本号
    """
    kappa: int = 128
    d: int = 128
    q: int = 2**32 - 99  # 4294967197 (素数)
    gamma: float = 2.0
    std_dev: float = 3.2
    max_small_coeff: int = 2
    rlwe_bound: int = 2
    version: str = "1.0.0"

    def __post_init__(self):
        """验证参数的合理性"""
        if not SAGE_AVAILABLE:
            # 如果 SageMath 不可用，只做基本验证
            if self.d <= 0 or self.q <= 0 or self.kappa <= 0:
                raise ValueError("参数必须为正数")
            return

        # 验证 q 是素数
        if not sg.is_prime(self.q):
            raise ValueError(f"q = {self.q} 必须是素数")

        # 验证 d 是 2 的幂（对 NTT 优化有利，非必需）
        if self.d & (self.d - 1) != 0:
            import warnings
            warnings.warn(f"d = {self.d} 不是 2 的幂，可能影响性能")

    def get_ring_dimension(self) -> int:
        """获取多项式环维度"""
        return self.d

    def get_modulus(self) -> int:
        """获取模数"""
        return self.q

    def get_rejection_param(self) -> float:
        """获取拒绝采样参数"""
        return self.gamma

    def to_dict(self) -> dict:
        """转换为字典格式（用于序列化）"""
        return {
            "kappa": self.kappa,
            "d": self.d,
            "q": self.q,
            "gamma": self.gamma,
            "std_dev": self.std_dev,
            "max_small_coeff": self.max_small_coeff,
            "rlwe_bound": self.rlwe_bound,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LanternParams:
        """从字典创建参数集"""
        return cls(**data)


# 默认参数集实例
DEFAULT_PARAMS = LanternParams()


# =============================================================================
# 预定义参数集（不同安全级别）
# =============================================================================

PARAMS_FAST = LanternParams(
    kappa=80,
    d=64,
    q=2**31 - 1,
    gamma=1.5,
    std_dev=2.0,
    version="fast-0.1.0"
)

PARAMS_STANDARD = DEFAULT_PARAMS

PARAMS_HIGH_SECURITY = LanternParams(
    kappa=256,
    d=256,
    q=2**40 - 87,
    gamma=3.0,
    std_dev=4.5,
    version="high-1.0.0"
)


# =============================================================================
# 全局参数管理
# =============================================================================

class ParamsManager:
    """全局参数管理器

    单例模式，管理当前活动的参数集
    """
    _instance: Optional['ParamsManager'] = None
    _current_params: LanternParams = DEFAULT_PARAMS

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_current(cls) -> LanternParams:
        """获取当前参数集"""
        return cls._current_params

    @classmethod
    def set_params(cls, params: LanternParams) -> None:
        """设置当前参数集"""
        cls._current_params = params

    @classmethod
    def use_preset(cls, preset: str) -> None:
        """使用预定义参数集

        Args:
            preset: 'fast', 'standard', 或 'high_security'
        """
        presets = {
            'fast': PARAMS_FAST,
            'standard': PARAMS_STANDARD,
            'high_security': PARAMS_HIGH_SECURITY,
        }
        if preset not in presets:
            raise ValueError(f"未知的预设参数集: {preset}")
        cls._current_params = presets[preset]


# 便捷访问函数
def get_params() -> LanternParams:
    """获取当前参数集"""
    return ParamsManager.get_current()


def set_params(params: LanternParams) -> None:
    """设置当前参数集"""
    ParamsManager.set_params(params)


# =============================================================================
# 统一随机源管理
# =============================================================================

class RandomSource:
    """统一的随机源管理器

    确保 Python、NumPy 和 Sage 的随机源都使用相同的种子，
    从而保证证明生成的可重现性
    """
    _current_seed: Optional[int] = None

    @classmethod
    def set_seed(cls, seed: int) -> None:
        """设置所有随机源的种子

        Args:
            seed: 随机种子（非负整数）

        Effects:
            - 设置 Python random 模块种子
            - 设置 NumPy 随机种子
            - 设置 Sage 随机种子（如果可用）
        """
        if seed < 0:
            raise ValueError("种子必须是非负整数")

        cls._current_seed = seed

        # 设置 Python random 种子
        random.seed(seed)

        # 设置 NumPy 种子
        np.random.seed(seed)

        # 设置 Sage 种子（如果可用）
        if SAGE_AVAILABLE:
            sg.set_random_seed(seed)

    @classmethod
    def get_current_seed(cls) -> Optional[int]:
        """获取当前种子（如果已设置）"""
        return cls._current_seed

    @classmethod
    def reset_seed(cls) -> None:
        """重置随机源（使用系统熵）"""
        cls._current_seed = None
        random.seed()
        np.random.seed()
        if SAGE_AVAILABLE:
            sg.set_random_seed()


# 便捷访问函数
def set_random_seed(seed: int) -> None:
    """设置统一随机种子

    这是推荐的设置随机源的方式，会同步设置所有底层随机数生成器

    Args:
        seed: 随机种子

    Example:
        >>> from lantern_zk.params import set_random_seed
        >>> set_random_seed(42)
        >>> # 现在所有证明生成都是可重现的
    """
    RandomSource.set_seed(seed)


def get_random_seed() -> Optional[int]:
    """获取当前随机种子（如果已设置）"""
    return RandomSource.get_current_seed()


def reset_random_seed() -> None:
    """重置随机源到非确定性状态"""
    RandomSource.reset_seed()


# =============================================================================
# 挑战生成参数
# =============================================================================

@dataclass
class ChallengeParams:
    """挑战参数配置

    用于 Fiat-Shamir 变换和交互式证明中的挑战生成
    """
    hash_algorithm: str = "sha3_256"
    challenge_space_bits: int = 256
    max_rejection_attempts: int = 100

    def to_dict(self) -> dict:
        return {
            "hash_algorithm": self.hash_algorithm,
            "challenge_space_bits": self.challenge_space_bits,
            "max_rejection_attempts": self.max_rejection_attempts,
        }


DEFAULT_CHALLENGE_PARAMS = ChallengeParams()


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    # 参数类
    "LanternParams",
    "ParamsManager",
    "ChallengeParams",

    # 预定义参数集
    "DEFAULT_PARAMS",
    "PARAMS_FAST",
    "PARAMS_STANDARD",
    "PARAMS_HIGH_SECURITY",
    "DEFAULT_CHALLENGE_PARAMS",

    # 参数管理函数
    "get_params",
    "set_params",

    # 随机源管理
    "RandomSource",
    "set_random_seed",
    "get_random_seed",
    "reset_random_seed",

    # 常量
    "SAGE_AVAILABLE",
]
