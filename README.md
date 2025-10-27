# Lantern 承诺验证系统

基于 Lantern RLWE 的零知识承诺和验证系统，支持向量数据的隐私保护审查流程。

## 概述

本项目实现了一个完整的承诺-验证工作流：
1. **被验证者**输入一个向量到系统
2. **验证者**提出验证规则
3. **被验证者**可以同意或拒绝审查
4. 如果同意，进行加密 ZKP 流程
5. **验证平台**给出验证结果，明文数据始终保持加密

## 系统架构

```
lantern_zk/                  # 核心模块包
├── __init__.py              # 统一导出接口
├── core.py                  # Lantern RLWE 原语（加密、密钥生成等）
├── commitments.py           # RLWE 向量承诺方案（支持多块、序列化）
├── params.py               # 全局参数和随机源管理
├── rules.py                # 规则 DSL 定义和解析（15+ 种规则类型）
├── proofs.py               # Lantern 子证明模块（ABDLOP、MLWE）
└── package.py              # 承诺证明包组合器（端到端接口）

lantern_commit_system.py    # CLI 主程序（完整 Lantern RLWE 实现）
demo_lantern_system.py       # 系统演示脚本
test_cli_workflow.py         # CLI 端到端测试
quickstart.py                # 环境验证脚本
lattice_zk_module.py         # 底层 SageMath 实现
```

## 环境配置

### 1. 安装 SageMath

**macOS (Homebrew):**
```bash
brew install --cask sage
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install sagemath
```

**其他平台：**
访问 [SageMath 官网](https://www.sagemath.org/download.html) 下载安装包

### 2. 验证安装

```bash
sage --version
```

### 3. 安装 Python 依赖（可选）

```bash
pip install -r requirements.txt
```

## 使用说明

### 快速开始

首先运行环境验证脚本：

```bash
sage -python quickstart.py
```

运行系统演示：

```bash
sage -python demo_lantern_system.py
```

### CLI 工具完整用法

使用 `sage -python` 运行 CLI 工具：

#### 1. 生成证明（证明者）

```bash
# 基本用法：直接提供向量
sage -python lantern_commit_system.py prover \
  --vector "1,0,0,0" \
  --rules rules_sample.json \
  --output proof.json

# 从文件加载向量
sage -python lantern_commit_system.py prover \
  --vector-file my_vector.json \
  --rules rules_sample.json \
  --output proof.json

# 使用种子确保可重现性
sage -python lantern_commit_system.py prover \
  --vector "1,0,0,0" \
  --rules rules_sample.json \
  --output proof.json \
  --seed 42 \
  --prover-id alice

# 自动接受所有规则（不提示）
sage -python lantern_commit_system.py prover \
  --vector "1,0,0,0" \
  --rules rules_sample.json \
  --output proof.json \
  --auto-accept
```

#### 2. 验证证明（验证者）

```bash
# 基本用法
sage -python lantern_commit_system.py verify \
  --proof proof.json \
  --rules rules_sample.json

# 详细输出
sage -python lantern_commit_system.py verify \
  --proof proof.json \
  --rules rules_sample.json \
  --verbose

# 如果证明包中已包含规则，可省略 --rules
sage -python lantern_commit_system.py verify \
  --proof proof.json
```

#### 3. 查看帮助

```bash
# 主帮助
sage -python lantern_commit_system.py --help

# Prover 帮助
sage -python lantern_commit_system.py prover --help

# Verify 帮助
sage -python lantern_commit_system.py verify --help
```

### 规则定义示例

在 `rules_sample.json` 中定义验证规则：

```json
{
  "rules": [
    {
      "id": "sum1",
      "type": "sum_equals",
      "value": 1
    },
    {
      "id": "no_c",
      "type": "coordinate_zero",
      "index": 2
    }
  ]
}
```

### 在 Python 代码中使用（编程接口）

```python
# 确保在 SageMath 环境中运行
from lantern_zk import (
    generate_commitment_package,
    verify_commitment_package,
    RuleSet,
    sum_equals_rule,
    coordinate_zero_rule,
    set_random_seed,
)

# 设置随机种子
set_random_seed(42)

# 定义向量和规则
vector = [1, 0, 0, 0]
rules = RuleSet()
rules.add_rule(sum_equals_rule("sum1", value=1))
rules.add_rule(coordinate_zero_rule("no_c", index=2))

# 生成证明包
package = generate_commitment_package(
    vector,
    rules,
    seed=42,
    prover_id="alice"
)

# 保存证明包
package.save("my_proof.json")

# 验证证明包
is_valid = verify_commitment_package(package, verbose=True)
print(f"验证结果: {'通过' if is_valid else '失败'}")
```

### 支持的规则类型

系统支持 15+ 种规则类型，包括：

| 规则类型 | 说明 | 参数示例 |
|---------|------|---------|
| `sum_equals` | 向量和等于目标值 | `value: 1` |
| `coordinate_zero` | 指定坐标为零 | `index: 2` |
| `coordinate_equals` | 坐标等于目标值 | `index: 0, value: 1` |
| `weighted_sum` | 加权和 | `weights: [1,2,3], value: 6` |
| `l2_norm_bound` | L2 范数边界 | `bound: 10.0` |
| `l1_norm_bound` | L1 范数边界 | `bound: 5` |
| `linf_norm_bound` | L∞ 范数边界 | `bound: 3` |
| `all_in_range` | 所有坐标在范围内 | `min: 0, max: 10` |
| `coordinate_in_range` | 单个坐标在范围内 | `index: 0, min: 0, max: 1` |
| `inner_product` | 内积等于目标值 | `vector: [1,2], value: 5` |

更多规则类型详见 `lantern_zk/rules.py`。

## 开发路线图

Lantern RLWE 实现已基本完成：

- [x] 任务 1: 整理项目结构与依赖
- [x] 任务 2: 参数与随机源统一接口
- [x] 任务 3: 向量嵌入与 RLWE 承诺底层扩展
- [x] 任务 4: Lantern 规则 DSL 定义与解析
- [x] 任务 5: Lantern 子证明模块化
- [x] 任务 6: 向量承诺 + 规则证明组合器
- [x] 任务 7: CLI 与交互流程更新
- [ ] 任务 8: 测试与示例（进行中）
- [ ] 任务 9: 文档与后续扩展说明

**当前完成度**: 78% (7/9 任务)

详细进度请参考 `PROGRESS.md` 和 `SUMMARY.md`。

## 技术细节

### RLWE 参数

- **安全参数 κ**: 128
- **多项式环维度 d**: 128
- **模数 q**: 2^32 - 99 (素数)
- **多项式环**: R = Z[X]/(X^d + 1)

### 承诺方案

当前使用基于 Lantern RLWE 加密的承诺：
1. 向量序列化为 JSON 并转换为比特串
2. 使用 RLWE 加密比特串
3. 密文作为承诺，私钥作为 opening

### 后续计划

- 实现完整的 ABDLOP/MLWE 子证明
- 支持复杂规则组合（线性约束、范数约束等）
- 批量验证优化
- 门限计票应用

## 许可证

[请根据项目实际情况添加]

## 参考文献

基于格基 Lantern ZK 方案，详见 `lattice-zk.ipynb` 和 `2022-284.pdf`。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

[请根据项目实际情况添加]
