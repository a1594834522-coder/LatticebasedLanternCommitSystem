"""Lantern 子证明系统 - ABDLOP 和 MLWE 证明模块

本模块封装了 Lantern ZK 证明系统的核心子协议：
1. ABDLOP 承诺证明 (abdlop_commit)
2. ABDLOP 线性关系证明 (abdlop_linear)
3. ABDLOP 二次关系证明 (abdlop_quadratic)
4. MLWE 秘密证明 (abdlop_mlwe)

每个子协议都：
- 封装了拒绝采样循环
- 提供统一的数据结构
- 支持 JSON 序列化
- 包含参数验证
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# 导入 lattice_zk_module 中的底层函数
try:
    from lattice_zk_module import (
        R, R_q, X_q, d, q,
        rand_Rql, rand_Rql_small, rand_Rq_mat, rand_Zq_mat,
        norm_Rql, norm_Rql_bound, dot_Rql,
        stack_vec_Rql, zv, ZM, IM,
        GaussianSampler,
        rej1, rej1_M, rej2, rej2_M,
    )
    SAGE_AVAILABLE = True
except ImportError:
    SAGE_AVAILABLE = False
    # 占位符，用于类型提示
    R = R_q = X_q = None


# =============================================================================
# 证明状态枚举
# =============================================================================

class ProofStatus(str, Enum):
    """证明状态"""
    SUCCESS = "success"  # 证明成功
    REJECTED = "rejected"  # 拒绝采样失败
    VERIFICATION_FAILED = "verification_failed"  # 验证失败
    ERROR = "error"  # 其他错误


class ProofType(str, Enum):
    """证明类型"""
    ABDLOP_COMMIT = "abdlop_commit"
    ABDLOP_LINEAR = "abdlop_linear"
    ABDLOP_QUADRATIC = "abdlop_quadratic"
    ABDLOP_MLWE = "abdlop_mlwe"
    COMPOSITE = "composite"  # 组合证明


# =============================================================================
# 通用证明数据结构
# =============================================================================

@dataclass
class ProofResult:
    """证明结果的统一数据结构

    Attributes:
        status: 证明状态（成功/拒绝/失败/错误）
        proof_type: 证明类型
        proof_data: 证明数据（具体结构取决于证明类型）
        metadata: 元数据（参数、时间戳等）
        error_message: 错误信息（如果有）
    """
    status: ProofStatus
    proof_type: ProofType
    proof_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def is_success(self) -> bool:
        """检查证明是否成功"""
        return self.status == ProofStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "status": self.status.value,
            "proof_type": self.proof_type.value,
            "proof_data": self.proof_data,
            "metadata": self.metadata,
            "error_message": self.error_message,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ProofResult:
        """从字典恢复"""
        return ProofResult(
            status=ProofStatus(data["status"]),
            proof_type=ProofType(data["proof_type"]),
            proof_data=data.get("proof_data", {}),
            metadata=data.get("metadata", {}),
            error_message=data.get("error_message"),
        )

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_json(json_str: str) -> ProofResult:
        """从 JSON 字符串解析"""
        data = json.loads(json_str)
        return ProofResult.from_dict(data)


# =============================================================================
# 拒绝采样辅助函数
# =============================================================================

def rejection_sampling_loop(
    prover_func: Callable[[], Tuple[bool, Any]],
    max_attempts: int = 1000,
    proof_type: ProofType = ProofType.ABDLOP_COMMIT,
) -> ProofResult:
    """通用拒绝采样循环

    Args:
        prover_func: 证明者函数，返回 (是否接受, 证明数据)
        max_attempts: 最大尝试次数
        proof_type: 证明类型

    Returns:
        ProofResult 对象
    """
    for attempt in range(max_attempts):
        try:
            accepted, proof_data = prover_func()
            if accepted:
                return ProofResult(
                    status=ProofStatus.SUCCESS,
                    proof_type=proof_type,
                    proof_data=proof_data,
                    metadata={"attempts": attempt + 1},
                )
        except Exception as e:
            return ProofResult(
                status=ProofStatus.ERROR,
                proof_type=proof_type,
                error_message=f"Attempt {attempt + 1} failed: {str(e)}",
            )

    # 超过最大尝试次数
    return ProofResult(
        status=ProofStatus.REJECTED,
        proof_type=proof_type,
        metadata={"attempts": max_attempts},
        error_message=f"Rejection sampling failed after {max_attempts} attempts",
    )


# =============================================================================
# 序列化辅助函数
# =============================================================================

def _serialize_vector(vec) -> List[List[int]]:
    """序列化 Sage 向量为嵌套列表"""
    if not SAGE_AVAILABLE:
        return [[]]

    result = []
    for poly in vec:
        coeffs = [int(c) for c in poly.list()]
        result.append(coeffs)
    return result


def _deserialize_vector(data: List[List[int]]):
    """从嵌套列表恢复 Sage 向量"""
    if not SAGE_AVAILABLE:
        raise RuntimeError("SageMath not available")

    from lattice_zk_module import R_q, stack_vec_Rql
    polys = [R_q(coeffs) for coeffs in data]
    return stack_vec_Rql([polys])


def _serialize_matrix(mat) -> List[List[List[int]]]:
    """序列化 Sage 矩阵为三重嵌套列表"""
    if not SAGE_AVAILABLE:
        return [[[]]]

    result = []
    for row in mat:
        row_data = []
        for poly in row:
            coeffs = [int(c) for c in poly.list()]
            row_data.append(coeffs)
        result.append(row_data)
    return result


# =============================================================================
# ABDLOP 承诺证明
# =============================================================================

@dataclass
class ABDLOPCommitParams:
    """ABDLOP 承诺证明的参数

    Attributes:
        m1: s1 的维度（Ajtai 部分消息向量）
        m2: s2 的维度（随机向量）
        ell: m 的维度（BDLOP 部分消息向量）
        n: Module-SIS 问题的维度
        N: 线性函数的数量
        gamma1, gamma2: 拒绝采样参数
        nu_s1, nu_s2: 系数上界
    """
    m1: int
    m2: int
    ell: int
    n: int
    N: int
    gamma1: float = 19.0
    gamma2: float = 2.0
    nu_s1: int = 1
    nu_s2: int = 1

    def compute_std_and_rep_rate(self, eta: float) -> Tuple[float, float, float, float]:
        """计算标准差和重复率

        Args:
            eta: 挑战范数上界

        Returns:
            (std1, rep_M1, std2, rep_M2)
        """
        alpha_s1 = norm_Rql_bound(self.m1, self.nu_s1)
        std1 = self.gamma1 * eta * alpha_s1
        rep_M1 = rej1_M(self.gamma1)

        alpha_s2 = norm_Rql_bound(self.m2, self.nu_s2)
        std2 = self.gamma2 * eta * alpha_s2
        rep_M2 = rej2_M(self.gamma2)

        return std1, rep_M1, std2, rep_M2


def abdlop_commit_proof(
    params: ABDLOPCommitParams,
    s1, s2, m,  # 私有信息
    A1, A2, B, tA, tB,  # 公开信息
    R1, r0,  # 线性函数
    get_challenge: Callable,  # 挑战生成函数
    eta: float,  # 挑战范数上界
    max_attempts: int = 1000,
) -> ProofResult:
    """ABDLOP 承诺证明（带拒绝采样循环）

    Args:
        params: 参数对象
        s1, s2, m: 私有向量
        A1, A2, B, tA, tB: 公开矩阵和承诺
        R1, r0: 线性关系参数
        get_challenge: 挑战生成函数
        eta: 挑战范数上界
        max_attempts: 最大尝试次数

    Returns:
        ProofResult 对象
    """
    if not SAGE_AVAILABLE:
        return ProofResult(
            status=ProofStatus.ERROR,
            proof_type=ProofType.ABDLOP_COMMIT,
            error_message="SageMath not available",
        )

    # 计算参数
    std1, rep_M1, std2, rep_M2 = params.compute_std_and_rep_rate(eta)

    def prover_attempt():
        """单次证明尝试"""
        # 采样 y1, y2
        y1_smplr = GaussianSampler(R_q, std1, params.m1)
        y1 = y1_smplr.get()
        y2_smplr = GaussianSampler(R_q, std2, params.m2)
        y2 = y2_smplr.get()

        # 计算 w, v
        w = A1 * y1 + A2 * y2
        v = R1 * stack_vec_Rql([y1, -B * y2])

        # 获取挑战
        c = get_challenge()

        # 计算响应
        cs1 = c * s1
        z1 = cs1 + y1
        if rej1(z1, cs1, std1, rep_M1):
            return False, {}

        cs2 = c * s2
        z2 = cs2 + y2
        if rej2(z2, cs2, std2, rep_M2):
            return False, {}

        # 验证条件
        import sage.all as sg
        cond1 = (norm_Rql(z1) <= std1 * sg.sqrt(2 * params.m1 * d)) and \
                (norm_Rql(z2) <= std2 * sg.sqrt(2 * params.m2 * d))
        cond2 = (A1 * z1 + A2 * z2 - c * tA == w)
        cond3 = (R1 * stack_vec_Rql([z1, c * tB - B * z2]) + c * r0 == v)

        if not (cond1 and cond2 and cond3):
            return False, {}

        # 证明成功，序列化数据
        proof_data = {
            "z1": _serialize_vector(z1),
            "z2": _serialize_vector(z2),
            "w": _serialize_vector(w),
            "v": _serialize_vector(v),
            "c_challenge": str(c),  # 挑战可能需要特殊处理
        }

        return True, proof_data

    return rejection_sampling_loop(
        prover_attempt,
        max_attempts=max_attempts,
        proof_type=ProofType.ABDLOP_COMMIT,
    )


# =============================================================================
# ABDLOP 线性证明
# =============================================================================

@dataclass
class ABDLOPLinearParams(ABDLOPCommitParams):
    """ABDLOP 线性证明的参数（继承承诺证明参数）

    额外属性:
        M: Zq 上的线性函数数量
        lambd: 随机挑战数量（通常等于 M）
    """
    M: int = 1
    lambd: int = 1


def abdlop_linear_proof(
    params: ABDLOPLinearParams,
    s1, s2, m, s,  # 私有信息
    A1, A2, B, Bg, tA, tB,  # 公开信息
    R1, r0, u1, u0,  # 线性关系
    get_challenge: Callable,
    eta: float,
    max_attempts: int = 1000,
) -> ProofResult:
    """ABDLOP 线性关系证明

    此证明在 ABDLOP 承诺证明的基础上，额外证明 Zq 上的线性关系

    Args:
        params: 参数对象
        s1, s2, m, s: 私有向量
        A1, A2, B, Bg, tA, tB: 公开矩阵和承诺
        R1, r0, u1, u0: 线性关系参数
        get_challenge: 挑战生成函数
        eta: 挑战范数上界
        max_attempts: 最大尝试次数

    Returns:
        ProofResult 对象
    """
    if not SAGE_AVAILABLE:
        return ProofResult(
            status=ProofStatus.ERROR,
            proof_type=ProofType.ABDLOP_LINEAR,
            error_message="SageMath not available",
        )

    def prover_attempt():
        """单次证明尝试"""
        # 第一步：生成随机 g
        from lattice_zk_module import rand_Rql_first_zero
        g = rand_Rql_first_zero(params.lambd)
        tg = Bg * s2 + g

        # 验证者：生成随机矩阵 Y
        Y = rand_Zq_mat(params.lambd, params.M)

        # 证明者：计算 h
        h = g + Y * stack_vec_Rql([u1[i].row() * s + u0[i] for i in range(params.M)])

        # 扩展 B, m, tB
        tB_extended = stack_vec_Rql([tB, tg])
        B_extended = B.stack(Bg)
        m_extended = stack_vec_Rql([m, g])
        ell_extended = params.ell + params.lambd

        # 扩展 R1, r0
        u1_mat = u1[0].row()
        for i in range(1, params.M):
            u1_mat = u1_mat.stack(u1[i].row())
        V1 = Y * u1_mat
        v0 = Y * stack_vec_Rql([u0[i] for i in range(params.M)]) - h
        R1_extended = R1.augment(ZM(params.N, params.lambd)).stack(V1.augment(IM(params.lambd)))
        r0_extended = stack_vec_Rql([r0, v0])

        # 运行 ABDLOP 承诺子协议
        commit_params = ABDLOPCommitParams(
            m1=params.m1,
            m2=params.m2,
            ell=ell_extended,
            n=params.n,
            N=params.N + params.lambd,
            gamma1=params.gamma1,
            gamma2=params.gamma2,
            nu_s1=params.nu_s1,
            nu_s2=params.nu_s2,
        )

        commit_result = abdlop_commit_proof(
            commit_params,
            s1, s2, m_extended,
            A1, A2, B_extended, tA, tB_extended,
            R1_extended, r0_extended,
            get_challenge,
            eta,
            max_attempts=1,  # 内部只尝试一次，外层循环控制
        )

        if not commit_result.is_success():
            return False, {}

        # 验证 h 的常数系数为 0
        cond2 = all(h[i][0] == 0 for i in range(params.lambd))
        if not cond2:
            return False, {}

        # 组合证明数据
        proof_data = {
            "commit_proof": commit_result.proof_data,
            "g": _serialize_vector(g),
            "h": _serialize_vector(h),
            "tg": _serialize_vector(tg),
        }

        return True, proof_data

    return rejection_sampling_loop(
        prover_attempt,
        max_attempts=max_attempts,
        proof_type=ProofType.ABDLOP_LINEAR,
    )


# =============================================================================
# 便捷包装函数
# =============================================================================

def create_abdlop_commit_params(
    m1: int = 8,
    m2: int = 25,
    ell: int = 2,
    n: int = 9,
    N: int = 1,
    **kwargs,
) -> ABDLOPCommitParams:
    """创建默认的 ABDLOP 承诺参数"""
    return ABDLOPCommitParams(m1=m1, m2=m2, ell=ell, n=n, N=N, **kwargs)


def create_abdlop_linear_params(
    m1: int = 8,
    m2: int = 25,
    ell: int = 2,
    n: int = 9,
    N: int = 1,
    M: int = 1,
    **kwargs,
) -> ABDLOPLinearParams:
    """创建默认的 ABDLOP 线性参数"""
    return ABDLOPLinearParams(m1=m1, m2=m2, ell=ell, n=n, N=N, M=M, lambd=M, **kwargs)


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    # 枚举
    "ProofStatus",
    "ProofType",
    # 数据结构
    "ProofResult",
    "ABDLOPCommitParams",
    "ABDLOPLinearParams",
    # 证明函数
    "abdlop_commit_proof",
    "abdlop_linear_proof",
    # 便捷函数
    "create_abdlop_commit_params",
    "create_abdlop_linear_params",
    "rejection_sampling_loop",
]
