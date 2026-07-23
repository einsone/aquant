# CLI 工具使用指南

Aquant 提供了一套命令行工具，帮助你更高效地开发和测试量化策略。

## 安装

CLI 工具随 Aquant 一起安装：

```bash
uv sync
```

## 可用命令

### run - 运行策略

运行一个策略脚本：

```bash
uv run aquant run examples/dual_moving_average.py
```

### validate - 验证策略

检查策略脚本是否包含必需的组件：

```bash
uv run aquant validate my_strategy.py
```

验证内容：
- 是否包含 `Strategy` 类定义
- 是否包含 `main()` 函数
- 基本的语法检查

### optimize - 策略参数优化

使用网格搜索或遗传算法优化策略参数。

#### 网格搜索

```bash
uv run aquant optimize examples/dual_moving_average.py \
  --method grid \
  --param fast_period:5,10,20 \
  --param slow_period:30,60,120 \
  --metric sharpe
```

参数说明：
- `--method grid`: 使用网格搜索
- `--param NAME:VALUE1,VALUE2,...`: 定义参数范围（多个值）
- `--metric METRIC`: 优化目标（sharpe, total_return, calmar 等）

#### 遗传算法

```bash
uv run aquant optimize examples/dual_moving_average.py \
  --method genetic \
  --param fast_period:5-20 \
  --param slow_period:30-120 \
  --generations 50 \
  --population 20 \
  --metric sharpe
```

参数说明：
- `--method genetic`: 使用遗传算法
- `--param NAME:MIN-MAX`: 定义参数范围（区间）
- `--generations N`: 迭代代数（默认50）
- `--population N`: 种群大小（默认20）

#### Walk-Forward 分析

```bash
uv run aquant optimize examples/dual_moving_average.py \
  --method walk-forward \
  --param fast_period:5-20 \
  --param slow_period:30-120 \
  --train-period 180 \
  --test-period 60
```

参数说明：
- `--method walk-forward`: 使用 walk-forward 分析
- `--train-period N`: 训练期天数
- `--test-period N`: 测试期天数

### report - 生成回测报告

生成 HTML 格式的回测报告：

```bash
uv run aquant report result.pkl --output report.html
```

参数说明：
- `result.pkl`: 回测结果文件（pickle 格式）
- `--output`: 输出文件路径（默认 report.html）

报告包含：
- 净值曲线图
- 收益统计
- 风险指标
- 交易明细
- 持仓分析

### init - 创建策略模板

创建新策略的模板代码：

```bash
uv run aquant init my_strategy.py
```

可选模板类型：

```bash
# 简单策略模板
uv run aquant init my_strategy.py --template simple

# 多因子策略模板
uv run aquant init my_strategy.py --template multi-factor

# 配对交易策略模板
uv run aquant init my_strategy.py --template pairs-trading
```

## 配置文件

你可以创建 `.aquant.toml` 配置文件来设置默认参数：

```toml
[backtest]
initial_capital = 1000000
commission_rate = 0.0003
stamp_duty_rate = 0.001
slippage_rate = 0.0005

[data]
source = "alds"  # 或 "csv"
cache_dir = ".cache"

[optimization]
default_metric = "sharpe"
parallel = true
max_workers = 4
```

## 高级用法

### 批量回测

使用 Shell 脚本批量运行多个策略：

```bash
#!/bin/bash
for strategy in strategies/*.py; do
  echo "Running $strategy..."
  uv run aquant run "$strategy"
done
```

### 参数扫描

扫描参数空间并保存结果：

```bash
#!/bin/bash
for period in 10 20 30 40 50; do
  echo "Testing period=$period..."
  uv run aquant run my_strategy.py --param period=$period > results_$period.txt
done
```

### 自动化报告生成

优化后自动生成报告：

```bash
# 运行优化
uv run aquant optimize strategy.py --method grid \
  --param param1:1,2,3 \
  --output best_result.pkl

# 生成报告
uv run aquant report best_result.pkl --output best_report.html
```

## 环境变量

- `AQUANT_DATA_DIR`: 数据目录路径
- `AQUANT_CACHE_DIR`: 缓存目录路径
- `AQUANT_LOG_LEVEL`: 日志级别（DEBUG, INFO, WARNING, ERROR）

```bash
export AQUANT_DATA_DIR=/data/market
export AQUANT_LOG_LEVEL=INFO
uv run aquant run strategy.py
```

## 故障排除

### 数据源问题

如果遇到数据加载错误：

```bash
# 检查数据源配置
uv run aquant validate strategy.py

# 清空缓存
rm -rf .cache
```

### 内存问题

如果回测大量数据时内存不足：

```bash
# 减少并行度
export AQUANT_MAX_WORKERS=2

# 或分段回测
uv run aquant run strategy.py --start 2020-01-01 --end 2020-06-30
uv run aquant run strategy.py --start 2020-07-01 --end 2020-12-31
```

### 性能问题

如果回测速度慢：

```bash
# 启用性能分析
uv run python -m cProfile -o profile.stats -m aquant run strategy.py

# 查看性能瓶颈
uv run python -m pstats profile.stats
```

## 示例工作流

完整的策略开发工作流：

```bash
# 1. 创建策略模板
uv run aquant init my_momentum.py --template simple

# 2. 编辑策略代码
vim my_momentum.py

# 3. 验证策略
uv run aquant validate my_momentum.py

# 4. 运行回测
uv run aquant run my_momentum.py

# 5. 参数优化
uv run aquant optimize my_momentum.py \
  --method genetic \
  --param lookback:10-60 \
  --param top_n:3-10 \
  --output optimized.pkl

# 6. 生成报告
uv run aquant report optimized.pkl --output final_report.html

# 7. 查看报告
open final_report.html
```

## 相关文档

- [策略开发指南](./guide/01_basics.md)
- [优化工具详解](./optimization.md)
- [性能优化技巧](./performance.md)
