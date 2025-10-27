#!/usr/bin/env python3
"""Lantern RLWE 承诺验证系统 - 完整实现

这个模块提供了一个完整的、基于 Lantern RLWE 的承诺验证系统，替换了之前的
Pedersen 原型。它实现了"承诺 → 协商规则 → 证明 → 验证"的完整工作流。

与之前的 Pedersen 原型相比，本版本：
- 使用真正的 Lantern RLWE 承诺（基于格的密码学）
- 使用 ABDLOP 和 MLWE 子证明协议
- 支持更丰富的规则类型（15+ 种）
- 完整的序列化和版本控制
- 自动多项式拆分（支持大向量）

使用方法（CLI）：

* ``prover`` 子命令：
    - 接受向量（逗号分隔或 JSON 文件）
    - 接受规则文件（JSON 格式）
    - 生成证明包（JSON 输出）

* ``verify`` 子命令：
    - 读取证明包和规则文件
    - 验证所有规则
    - 报告每条规则的通过/失败状态

支持的规则类型：
- sum_equals: 向量和等于目标值
- coordinate_zero: 指定坐标为零
- coordinate_equals: 指定坐标等于目标值
- l2_norm_bound: L2 范数边界
- 更多规则类型详见 lantern_zk.rules 模块

示例：
    # 生成证明
    sage -python lantern_commit_system.py prover \\
        --vector "1,0,0,0" \\
        --rules rules.json \\
        --output proof.json

    # 验证证明
    sage -python lantern_commit_system.py verify \\
        --proof proof.json \\
        --rules rules.json

注意：本模块需要在 SageMath 环境中运行。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# 检查 SageMath 环境
try:
    from sage.all import *
    SAGE_AVAILABLE = True
except ImportError:
    print("错误: 此脚本需要在 SageMath 环境中运行", file=sys.stderr)
    print("请使用: sage -python lantern_commit_system.py", file=sys.stderr)
    SAGE_AVAILABLE = False

# 导入 Lantern 模块
try:
    from lantern_zk import (
        set_random_seed,
        generate_commitment_package,
        verify_commitment_package,
        LanternCommitmentPackage,
        RuleSet,
        sum_equals_rule,
        coordinate_zero_rule,
        coordinate_equals_rule,
        l2_norm_bound_rule,
        get_params,
    )
    LANTERN_AVAILABLE = True
except ImportError as e:
    print(f"错误: 无法导入 Lantern 模块: {e}", file=sys.stderr)
    print("请确保 lantern_zk 包在 PYTHONPATH 中", file=sys.stderr)
    LANTERN_AVAILABLE = False


# =============================================================================
# 向量解析和规则加载
# =============================================================================

def parse_vector_arg(value: str) -> List[int]:
    """解析向量参数

    支持两种格式：
    1. 逗号分隔: "1,0,0,0"
    2. JSON 数组: "[1, 0, 0, 0]"
    """
    value = value.strip()
    if value.startswith("["):
        vector = json.loads(value)
        return [int(x) for x in vector]
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def load_vector_from_file(path: Path) -> List[int]:
    """从文件加载向量（JSON 格式）"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [int(x) for x in data]
    elif isinstance(data, dict) and "vector" in data:
        return [int(x) for x in data["vector"]]
    else:
        raise ValueError("向量文件必须是 JSON 数组或包含 'vector' 键的对象")


def load_rules_file(path: Path) -> RuleSet:
    """从文件加载规则集

    使用 lantern_zk.RuleSet 的标准格式
    """
    return RuleSet.from_file(path)


def format_vector_preview(vector: Sequence[int], max_display: int = 20) -> str:
    """格式化向量预览（用于显示）"""
    if len(vector) <= max_display:
        return str(list(vector))
    else:
        preview = list(vector[:max_display])
        return f"{preview}... (共 {len(vector)} 个元素)"


# =============================================================================
# 证明者命令
# =============================================================================

def cmd_prover(args: argparse.Namespace) -> None:
    """证明者命令：生成承诺和证明包"""

    if not SAGE_AVAILABLE or not LANTERN_AVAILABLE:
        print("错误: 缺少必需的依赖", file=sys.stderr)
        sys.exit(1)

    # 1. 加载向量
    if args.vector_file:
        vector = load_vector_from_file(Path(args.vector_file))
    elif args.vector:
        vector = parse_vector_arg(args.vector)
    else:
        print("错误: 必须提供 --vector 或 --vector-file", file=sys.stderr)
        sys.exit(1)

    # 2. 加载规则
    try:
        rules = load_rules_file(Path(args.rules))
    except Exception as e:
        print(f"错误: 无法加载规则文件: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. 显示会话信息
    params = get_params()
    print("=" * 70)
    print("Lantern 证明者会话")
    print("=" * 70)
    print(f"参数集版本: {params.version}")
    print(f"环维度 d: {params.d}")
    print(f"模数 q: {params.q}")
    print(f"安全参数 κ: {params.kappa}")
    print()
    print(f"向量长度: {len(vector)}")
    print(f"向量预览: {format_vector_preview(vector)}")
    print()
    print(f"规则数量: {len(rules.rules)}")
    print("规则详情:")
    for rule in rules.rules:
        print(f"  - {rule.rule_id}: {rule.rule_type.value}")
        if rule.description:
            print(f"    描述: {rule.description}")
        print(f"    参数: {rule.params}")
    print()

    # 4. 确认生成证明
    if not args.auto_accept:
        decision = input("接受这些规则并生成证明？(yes/no) ").strip().lower()
        if decision not in {"y", "yes"}:
            print("已取消：证明者拒绝规则。")
            return

    # 5. 设置随机种子（如果提供）
    if args.seed is not None:
        set_random_seed(args.seed)
        print(f"使用随机种子: {args.seed}")

    # 6. 生成证明包
    print()
    print("生成承诺和证明...")
    try:
        package = generate_commitment_package(
            vector,
            rules,
            seed=args.seed,
            prover_id=args.prover_id,
        )
        print("✓ 证明包生成成功")
    except Exception as e:
        print(f"错误: 生成证明包失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 7. 检查所有证明是否成功
    if not package.all_proofs_successful():
        failed_rules = package.get_failed_rules()
        print(f"警告: 部分证明失败: {failed_rules}")
        for rule_id in failed_rules:
            proof = package.get_proof(rule_id)
            if proof and proof.error_message:
                print(f"  {rule_id}: {proof.error_message}")

    # 8. 保存到文件
    output_path = Path(args.output)
    try:
        package.save(output_path)
        print(f"✓ 证明已写入: {output_path}")
    except Exception as e:
        print(f"错误: 无法保存证明文件: {e}", file=sys.stderr)
        sys.exit(1)

    # 9. 显示统计信息
    print()
    print("证明包统计:")
    print(f"  承诺块数: {package.commitment.num_chunks()}")
    print(f"  总比特数: {package.commitment.total_bits}")
    print(f"  证明数量: {len(package.proofs)}")
    print(f"  成功证明: {sum(1 for p in package.proofs.values() if p.is_success())}")
    print()
    print("=" * 70)


# =============================================================================
# 验证者命令
# =============================================================================

def cmd_verify(args: argparse.Namespace) -> None:
    """验证者命令：验证证明包"""

    if not SAGE_AVAILABLE or not LANTERN_AVAILABLE:
        print("错误: 缺少必需的依赖", file=sys.stderr)
        sys.exit(1)

    # 1. 加载证明包
    try:
        package = LanternCommitmentPackage.load(Path(args.proof))
    except Exception as e:
        print(f"错误: 无法加载证明文件: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 加载规则（如果提供）
    if args.rules:
        try:
            rules = load_rules_file(Path(args.rules))
            # 替换证明包中的规则
            package.rules = rules
        except Exception as e:
            print(f"错误: 无法加载规则文件: {e}", file=sys.stderr)
            sys.exit(1)

    # 3. 显示验证信息
    print("=" * 70)
    print("Lantern 验证者会话")
    print("=" * 70)
    print(f"证明包版本: {package.metadata.get('params_version', 'unknown')}")
    print(f"创建时间: {package.metadata.get('created_at', 'unknown')}")
    print(f"证明者ID: {package.metadata.get('prover_id', 'anonymous')}")
    print()
    print(f"向量长度: {package.vector_length}")
    print(f"规则数量: {len(package.rules.rules)}")
    print(f"证明数量: {len(package.proofs)}")
    print()

    # 4. 验证证明包
    verbose = args.verbose
    print("验证证明...")
    print()

    try:
        is_valid = verify_commitment_package(package, verbose=verbose)
    except Exception as e:
        print(f"错误: 验证过程出错: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 5. 显示详细结果
    if not verbose:
        print("规则验证结果:")
        print("-" * 70)
        for rule in package.rules.rules:
            proof = package.get_proof(rule.rule_id)
            if proof is None:
                status = "缺失"
                symbol = "⚠️ "
            elif proof.is_success():
                status = "通过"
                symbol = "✓ "
            else:
                status = "失败"
                symbol = "✗ "

            print(f"{symbol}{rule.rule_id:20s} | {status:6s} | {rule.rule_type.value}")
            if proof and proof.error_message:
                print(f"     错误: {proof.error_message}")

    # 6. 显示总结
    print()
    print("=" * 70)
    if is_valid:
        print("✅ 验证结果: 所有规则验证通过")
        exit_code = 0
    else:
        print("❌ 验证结果: 存在未满足的规则")
        failed = package.get_failed_rules()
        if failed:
            print(f"   失败的规则: {', '.join(failed)}")
        exit_code = 1

    print("=" * 70)
    sys.exit(exit_code)


# =============================================================================
# CLI 构建
# =============================================================================

def build_cli() -> argparse.ArgumentParser:
    """构建 CLI 解析器"""

    parser = argparse.ArgumentParser(
        description="Lantern RLWE 承诺验证系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:

  # 生成证明
  sage -python lantern_commit_system.py prover \\
      --vector "1,0,0,0" \\
      --rules rules.json \\
      --output proof.json

  # 验证证明
  sage -python lantern_commit_system.py verify \\
      --proof proof.json \\
      --rules rules.json

  # 使用种子确保可重现性
  sage -python lantern_commit_system.py prover \\
      --vector "1,0,0,0" \\
      --rules rules.json \\
      --output proof.json \\
      --seed 42

更多信息请参考 README.md
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # Prover 子命令
    prover = subparsers.add_parser(
        "prover",
        help="生成承诺和零知识证明",
        description="证明者接口：生成向量的 RLWE 承诺和规则的 Lantern 证明"
    )
    prover.add_argument(
        "--vector",
        type=str,
        help="向量（逗号分隔或 JSON 数组格式）"
    )
    prover.add_argument(
        "--vector-file",
        type=str,
        help="从 JSON 文件加载向量"
    )
    prover.add_argument(
        "--rules",
        type=str,
        required=True,
        help="规则文件路径（JSON 格式）"
    )
    prover.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出证明包文件路径（JSON 格式）"
    )
    prover.add_argument(
        "--auto-accept",
        action="store_true",
        help="自动接受所有规则（不提示确认）"
    )
    prover.add_argument(
        "--seed",
        type=int,
        help="随机种子（用于可重现的证明生成）"
    )
    prover.add_argument(
        "--prover-id",
        type=str,
        help="证明者标识符（可选）"
    )

    # Verify 子命令
    verify = subparsers.add_parser(
        "verify",
        help="验证证明是否满足规则",
        description="验证者接口：验证证明包中的所有规则证明"
    )
    verify.add_argument(
        "--proof",
        type=str,
        required=True,
        help="证明包文件路径（JSON 格式）"
    )
    verify.add_argument(
        "--rules",
        type=str,
        help="规则文件路径（可选，如果证明包中已包含规则）"
    )
    verify.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细验证信息"
    )

    return parser


# =============================================================================
# 主入口
# =============================================================================

def main(argv: Optional[Sequence[str]] = None) -> None:
    """主函数"""

    # 检查环境
    if not SAGE_AVAILABLE:
        print("=" * 70)
        print("错误: SageMath 环境不可用")
        print("=" * 70)
        print()
        print("此脚本需要在 SageMath 环境中运行。")
        print()
        print("请尝试以下命令:")
        print("  sage -python lantern_commit_system.py --help")
        print()
        print("或者检查 SageMath 是否正确安装:")
        print("  sage --version")
        print()
        print("=" * 70)
        sys.exit(1)

    if not LANTERN_AVAILABLE:
        print("=" * 70)
        print("错误: Lantern 模块不可用")
        print("=" * 70)
        print()
        print("请确保 lantern_zk 包可以被导入。")
        print("尝试运行环境验证脚本:")
        print("  sage -python quickstart.py")
        print()
        print("=" * 70)
        sys.exit(1)

    # 解析命令行参数
    parser = build_cli()
    args = parser.parse_args(argv)

    # 分发到子命令
    if args.command == "prover":
        cmd_prover(args)
    elif args.command == "verify":
        cmd_verify(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
