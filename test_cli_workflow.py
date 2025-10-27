#!/usr/bin/env sage-python
"""端到端 CLI 工作流测试

本脚本测试更新后的 lantern_commit_system.py CLI 工具的完整工作流：
1. 创建测试向量和规则文件
2. 使用 prover 命令生成证明包
3. 使用 verify 命令验证证明
4. 测试成功和失败的场景

运行方式:
    sage -python test_cli_workflow.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple


def run_cli_command(args: List[str]) -> Tuple[int, str, str]:
    """运行 CLI 命令并返回结果

    Args:
        args: 命令行参数列表

    Returns:
        (返回码, stdout, stderr)
    """
    cmd = ["sage", "-python", "lantern_commit_system.py"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except Exception as e:
        return -1, "", str(e)


def test_basic_workflow():
    """测试基本工作流：向量满足规则"""
    print("=" * 70)
    print("测试 1: 基本工作流（成功场景）")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建规则文件
        rules_file = tmpdir / "rules.json"
        rules = {
            "rules": [
                {
                    "id": "sum1",
                    "type": "sum_equals",
                    "value": 1,
                    "description": "向量和等于1"
                },
                {
                    "id": "no_c",
                    "type": "coordinate_zero",
                    "index": 2,
                    "description": "第3个坐标为0"
                }
            ]
        }
        rules_file.write_text(json.dumps(rules, indent=2, ensure_ascii=False))
        print(f"✓ 创建规则文件: {rules_file}")

        # 生成证明
        proof_file = tmpdir / "proof.json"
        print("\n运行 prover 命令...")
        returncode, stdout, stderr = run_cli_command([
            "prover",
            "--vector", "1,0,0,0",
            "--rules", str(rules_file),
            "--output", str(proof_file),
            "--auto-accept",
            "--seed", "42",
        ])

        if returncode != 0:
            print(f"✗ prover 命令失败 (返回码: {returncode})")
            print("stdout:", stdout)
            print("stderr:", stderr)
            return False

        print(f"✓ prover 命令成功")
        print(f"✓ 证明文件: {proof_file}")

        if not proof_file.exists():
            print("✗ 证明文件未生成")
            return False

        # 验证证明
        print("\n运行 verify 命令...")
        returncode, stdout, stderr = run_cli_command([
            "verify",
            "--proof", str(proof_file),
            "--rules", str(rules_file),
        ])

        if returncode != 0:
            print(f"✗ verify 命令失败 (返回码: {returncode})")
            print("stdout:", stdout)
            print("stderr:", stderr)
            return False

        print(f"✓ verify 命令成功")

        # 检查输出中是否包含成功信息
        if "所有规则验证通过" in stdout or "验证通过" in stdout:
            print("✓ 验证结果：所有规则通过")
            return True
        else:
            print("✗ 验证结果不符合预期")
            print("输出:", stdout)
            return False


def test_failing_rules():
    """测试失败场景：向量不满足规则"""
    print("\n" + "=" * 70)
    print("测试 2: 失败场景（向量不满足规则）")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建规则文件（要求和为 10）
        rules_file = tmpdir / "rules_fail.json"
        rules = {
            "rules": [
                {
                    "id": "sum10",
                    "type": "sum_equals",
                    "value": 10,
                    "description": "向量和等于10"
                }
            ]
        }
        rules_file.write_text(json.dumps(rules, indent=2, ensure_ascii=False))
        print(f"✓ 创建规则文件: {rules_file}")

        # 生成证明（向量和为1，不满足规则）
        proof_file = tmpdir / "proof_fail.json"
        print("\n运行 prover 命令（向量不满足规则）...")
        returncode, stdout, stderr = run_cli_command([
            "prover",
            "--vector", "1,0,0,0",
            "--rules", str(rules_file),
            "--output", str(proof_file),
            "--auto-accept",
        ])

        # Prover 应该能生成证明，但证明会标记为失败
        if returncode != 0:
            print(f"✗ prover 命令失败 (返回码: {returncode})")
            return False

        print(f"✓ prover 命令完成（预期有警告）")

        if not proof_file.exists():
            print("✗ 证明文件未生成")
            return False

        # 验证证明（应该失败）
        print("\n运行 verify 命令（预期失败）...")
        returncode, stdout, stderr = run_cli_command([
            "verify",
            "--proof", str(proof_file),
            "--rules", str(rules_file),
        ])

        # 验证应该返回非零退出码
        if returncode == 0:
            print("✗ verify 命令应该失败但成功了")
            return False

        print(f"✓ verify 命令正确返回失败状态 (返回码: {returncode})")

        # 检查输出中是否包含失败信息
        if "存在未满足的规则" in stdout or "失败" in stdout:
            print("✓ 验证结果：正确识别规则不满足")
            return True
        else:
            print("✗ 验证输出不符合预期")
            print("输出:", stdout)
            return False


def test_vector_from_file():
    """测试从文件加载向量"""
    print("\n" + "=" * 70)
    print("测试 3: 从文件加载向量")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建向量文件
        vector_file = tmpdir / "vector.json"
        vector = [1, 0, 0, 0]
        vector_file.write_text(json.dumps(vector))
        print(f"✓ 创建向量文件: {vector_file}")

        # 创建规则文件
        rules_file = tmpdir / "rules.json"
        rules = {
            "rules": [
                {
                    "id": "sum1",
                    "type": "sum_equals",
                    "value": 1
                }
            ]
        }
        rules_file.write_text(json.dumps(rules, indent=2))
        print(f"✓ 创建规则文件: {rules_file}")

        # 生成证明
        proof_file = tmpdir / "proof.json"
        print("\n运行 prover 命令（从文件加载向量）...")
        returncode, stdout, stderr = run_cli_command([
            "prover",
            "--vector-file", str(vector_file),
            "--rules", str(rules_file),
            "--output", str(proof_file),
            "--auto-accept",
        ])

        if returncode != 0:
            print(f"✗ prover 命令失败 (返回码: {returncode})")
            print("stderr:", stderr)
            return False

        print(f"✓ prover 命令成功")

        # 验证证明
        returncode, stdout, stderr = run_cli_command([
            "verify",
            "--proof", str(proof_file),
        ])

        if returncode != 0:
            print(f"✗ verify 命令失败 (返回码: {returncode})")
            return False

        print(f"✓ verify 命令成功（证明包包含规则）")
        return True


def test_help_commands():
    """测试帮助命令"""
    print("\n" + "=" * 70)
    print("测试 4: 帮助命令")
    print("=" * 70)

    # 测试主帮助
    print("运行主帮助命令...")
    returncode, stdout, stderr = run_cli_command(["--help"])
    if returncode != 0 or "Lantern RLWE" not in stdout:
        print("✗ 主帮助命令失败")
        return False
    print("✓ 主帮助命令成功")

    # 测试 prover 帮助
    print("运行 prover 帮助命令...")
    returncode, stdout, stderr = run_cli_command(["prover", "--help"])
    if returncode != 0 or "生成承诺" not in stdout:
        print("✗ prover 帮助命令失败")
        return False
    print("✓ prover 帮助命令成功")

    # 测试 verify 帮助
    print("运行 verify 帮助命令...")
    returncode, stdout, stderr = run_cli_command(["verify", "--help"])
    if returncode != 0 or "验证证明" not in stdout:
        print("✗ verify 帮助命令失败")
        return False
    print("✓ verify 帮助命令成功")

    return True


def main():
    """主测试函数"""
    print()
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + " " * 15 + "Lantern CLI 端到端测试套件" + " " * 20 + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    tests = [
        ("基本工作流（成功）", test_basic_workflow),
        ("失败场景", test_failing_rules),
        ("从文件加载向量", test_vector_from_file),
        ("帮助命令", test_help_commands),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ 测试 '{name}' 出现异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {name:30s} {status}")

    all_passed = all(success for _, success in results)
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有测试通过！")
        print("\nCLI 系统已成功升级到 Lantern RLWE 实现。")
    else:
        print("⚠️  部分测试失败，请检查错误信息。")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
