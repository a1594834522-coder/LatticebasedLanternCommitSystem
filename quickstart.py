#!/usr/bin/env sage-python
"""Lantern ZK 系统快速验证脚本

运行方式:
    sage -python quickstart.py

或者在 SageMath 环境中:
    python quickstart.py
"""

def test_sage_environment():
    """测试 SageMath 环境是否可用"""
    print("🔍 检查 SageMath 环境...")
    try:
        import sage.all as sg
        print("✓ SageMath 导入成功")
        print(f"  版本: {sg.version.version}")
        return True
    except ImportError as e:
        print(f"✗ SageMath 导入失败: {e}")
        print("  请确保使用 'sage -python' 运行此脚本")
        return False


def test_lantern_module():
    """测试 Lantern 模块是否可用"""
    print("\n🔍 检查 Lantern 核心模块...")
    try:
        import lattice_zk_module
        print("✓ lattice_zk_module 导入成功")
        print(f"  参数: d={lattice_zk_module.d}, q={lattice_zk_module.q}")
        return True
    except ImportError as e:
        print(f"✗ lattice_zk_module 导入失败: {e}")
        return False


def test_lantern_zk_package():
    """测试 lantern_zk 包是否可用"""
    print("\n🔍 检查 lantern_zk 包...")
    try:
        import lantern_zk
        print("✓ lantern_zk 包导入成功")
        print(f"  可用函数: {', '.join(lantern_zk.__all__[:5])}...")
        return True
    except ImportError as e:
        print(f"✗ lantern_zk 包导入失败: {e}")
        return False


def test_commitment_basic():
    """测试基本的承诺功能"""
    print("\n🔍 测试 RLWE 承诺功能...")
    try:
        from lantern_zk import commit_vector, verify_commitment

        # 创建一个简单的向量承诺
        vector = [1, 2, 3]
        print(f"  输入向量: {vector}")

        commitment, opening = commit_vector(vector, seed=42)
        print("✓ 承诺生成成功")

        # 验证承诺
        is_valid = verify_commitment(commitment, opening, vector)
        if is_valid:
            print("✓ 承诺验证成功")
            return True
        else:
            print("✗ 承诺验证失败")
            return False
    except Exception as e:
        print(f"✗ 承诺测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_encryption_basic():
    """测试基本的加密功能"""
    print("\n🔍 测试 Lantern 加密功能...")
    try:
        from lantern_zk import lantern_keygen, lantern_encrypt, lantern_decrypt

        # 生成密钥对
        pubkey, secret = lantern_keygen(bound=2)
        print("✓ 密钥生成成功")

        # 加密消息
        message_bits = [1, 0, 1, 1, 0, 0, 1, 0]
        ciphertext = lantern_encrypt(pubkey, message_bits, bound=2)
        print(f"✓ 加密成功 (消息长度: {len(message_bits)} bits)")

        # 解密消息
        decrypted_bits, _ = lantern_decrypt(secret, ciphertext, len(message_bits))
        if list(decrypted_bits[:len(message_bits)]) == message_bits:
            print("✓ 解密成功且消息匹配")
            return True
        else:
            print("✗ 解密后消息不匹配")
            return False
    except Exception as e:
        print(f"✗ 加密测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Lantern ZK 系统环境验证")
    print("=" * 60)

    tests = [
        test_sage_environment,
        test_lantern_module,
        test_lantern_zk_package,
        test_encryption_basic,
        test_commitment_basic,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ 测试出错: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print(f"测试结果: {sum(results)}/{len(results)} 通过")
    print("=" * 60)

    if all(results):
        print("\n🎉 所有测试通过！系统配置正确。")
        print("\n下一步:")
        print("  1. 查看 README.md 了解使用方法")
        print("  2. 运行 CLI: sage -python lantern_commit_system.py --help")
        print("  3. 参考 rules_sample.json 创建自定义规则")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查环境配置。")
        print("  参考 README.md 中的环境配置说明")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
