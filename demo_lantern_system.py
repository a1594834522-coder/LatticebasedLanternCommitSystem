#!/usr/bin/env sage-python
"""Lantern 承诺验证系统 - 完整演示

本脚本演示了新的 Lantern 系统的完整工作流：
1. 创建向量和规则
2. 生成承诺证明包
3. 验证证明包
4. 序列化和反序列化

运行方式:
    sage -python demo_lantern_system.py
"""

import sys
from pathlib import Path


def demo_basic_workflow():
    """演示基本工作流"""
    print("=" * 70)
    print("Lantern 系统演示 - 基本工作流")
    print("=" * 70)

    try:
        from lantern_zk import (
            set_random_seed,
            generate_commitment_package,
            verify_commitment_package,
            RuleSet,
            sum_equals_rule,
            coordinate_zero_rule,
        )
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保在 SageMath 环境中运行此脚本")
        return False

    # 设置随机种子（可重现）
    set_random_seed(42)
    print("\n✓ 设置随机种子: 42")

    # 定义向量
    vector = [1, 0, 0, 0]
    print(f"✓ 定义向量: {vector}")

    # 创建规则集
    rules = RuleSet()
    rules.add_rule(sum_equals_rule("sum1", value=1, description="向量和等于1"))
    rules.add_rule(coordinate_zero_rule("no_c", index=2, description="第3个坐标为0"))
    print(f"✓ 创建规则集: {len(rules.rules)} 条规则")
    for rule in rules.rules:
        print(f"   - {rule.rule_id}: {rule.description}")

    # 生成承诺证明包
    print("\n🔐 生成承诺证明包...")
    try:
        package = generate_commitment_package(
            vector,
            rules,
            seed=42,
            prover_id="demo_prover",
        )
        print(f"✓ 证明包生成成功")
        print(f"   - 承诺块数: {package.commitment.num_chunks()}")
        print(f"   - 证明数量: {len(package.proofs)}")
        print(f"   - 所有证明成功: {package.all_proofs_successful()}")
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 验证证明包
    print("\n🔍 验证证明包...")
    try:
        is_valid = verify_commitment_package(package, verbose=True)
        if is_valid:
            print("✅ 验证通过！")
        else:
            print("❌ 验证失败！")
            return False
    except Exception as e:
        print(f"❌ 验证出错: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 保存到文件
    output_file = "demo_package.json"
    print(f"\n💾 保存证明包到 {output_file}...")
    try:
        package.save(output_file)
        print(f"✓ 保存成功")

        # 从文件加载
        print(f"\n📂 从文件加载证明包...")
        loaded_package = package.__class__.load(output_file)
        print(f"✓ 加载成功")

        # 验证加载的包
        is_valid_loaded = verify_commitment_package(loaded_package, verbose=False)
        print(f"✓ 加载的包验证: {'通过' if is_valid_loaded else '失败'}")

    except Exception as e:
        print(f"❌ 文件操作失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 70)
    print("✅ 演示完成！")
    print("=" * 70)
    return True


def demo_rule_parsing():
    """演示规则解析"""
    print("\n" + "=" * 70)
    print("Lantern 系统演示 - 规则解析")
    print("=" * 70)

    try:
        from lantern_zk import RuleSet
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

    # 从文件加载规则
    rules_file = "rules_sample.json"
    if not Path(rules_file).exists():
        print(f"⚠️  规则文件 {rules_file} 不存在，跳过此演示")
        return True

    print(f"\n📂 从文件加载规则: {rules_file}")
    try:
        rules = RuleSet.from_file(rules_file)
        print(f"✓ 加载成功: {len(rules.rules)} 条规则")

        for rule in rules.rules:
            print(f"\n规则: {rule.rule_id}")
            print(f"  类型: {rule.rule_type.value}")
            print(f"  参数: {rule.params}")
            print(f"  协议: {rule.get_protocol().value}")

    except Exception as e:
        print(f"❌ 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def demo_parameter_management():
    """演示参数管理"""
    print("\n" + "=" * 70)
    print("Lantern 系统演示 - 参数管理")
    print("=" * 70)

    try:
        from lantern_zk import (
            get_params,
            set_params,
            PARAMS_FAST,
            PARAMS_STANDARD,
            PARAMS_HIGH_SECURITY,
        )
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

    # 显示当前参数
    print("\n当前参数集:")
    params = get_params()
    print(f"  版本: {params.version}")
    print(f"  d (环维度): {params.d}")
    print(f"  q (模数): {params.q}")
    print(f"  κ (安全参数): {params.kappa}")
    print(f"  γ (拒绝采样): {params.gamma}")

    # 显示可用的预设参数
    print("\n可用的预设参数:")
    for name, preset in [
        ("快速", PARAMS_FAST),
        ("标准", PARAMS_STANDARD),
        ("高安全", PARAMS_HIGH_SECURITY),
    ]:
        print(f"  {name}: d={preset.d}, q={preset.q}, κ={preset.kappa}")

    return True


def demo_commitment_features():
    """演示承诺功能"""
    print("\n" + "=" * 70)
    print("Lantern 系统演示 - 承诺功能")
    print("=" * 70)

    try:
        from lantern_zk import (
            commit_vector,
            open_commitment,
            verify_commitment,
            set_random_seed,
        )
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

    set_random_seed(42)

    # 测试小向量
    print("\n测试 1: 小向量")
    small_vector = [1, 2, 3, 4, 5]
    print(f"  向量: {small_vector}")
    commitment, opening = commit_vector(small_vector, seed=42)
    print(f"  承诺块数: {commitment.num_chunks()}")
    print(f"  总比特数: {commitment.total_bits}")

    # 验证
    is_valid = verify_commitment(commitment, opening, small_vector)
    print(f"  验证结果: {'✓ 通过' if is_valid else '✗ 失败'}")

    # 打开承诺
    recovered = open_commitment(commitment, opening)
    print(f"  恢复向量: {recovered}")
    print(f"  匹配原向量: {recovered == small_vector}")

    # 测试大向量（需要多块）
    print("\n测试 2: 大向量（自动拆分）")
    # 创建一个可能需要多块的向量
    large_vector = list(range(20))
    print(f"  向量长度: {len(large_vector)}")
    commitment_large, opening_large = commit_vector(large_vector, seed=43)
    print(f"  承诺块数: {commitment_large.num_chunks()}")
    print(f"  总比特数: {commitment_large.total_bits}")

    is_valid_large = verify_commitment(commitment_large, opening_large, large_vector)
    print(f"  验证结果: {'✓ 通过' if is_valid_large else '✗ 失败'}")

    return True


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + " " * 15 + "Lantern 承诺验证系统 - 综合演示" + " " * 15 + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    demos = [
        ("基本工作流", demo_basic_workflow),
        ("规则解析", demo_rule_parsing),
        ("参数管理", demo_parameter_management),
        ("承诺功能", demo_commitment_features),
    ]

    results = []
    for name, demo_func in demos:
        try:
            success = demo_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} 演示出错: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 总结
    print("\n" + "=" * 70)
    print("演示总结")
    print("=" * 70)
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {name:20s} {status}")

    all_passed = all(success for _, success in results)
    print("\n" + ("=" * 70))
    if all_passed:
        print("🎉 所有演示均成功！")
        print("\n下一步:")
        print("  1. 查看生成的 demo_package.json 文件")
        print("  2. 尝试修改向量或规则，观察验证结果")
        print("  3. 参考 PROGRESS.md 了解更多信息")
    else:
        print("⚠️  部分演示失败，请检查错误信息")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
