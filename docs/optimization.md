# 策略优化工具

本文档介绍 aquant 提供的策略参数优化工具。

## 优化方法概览

| 方法 | 特点 | 适用场景 |
|------|------|---------|
| 网格搜索 | 遍历所有参数组合 | 参数空间小，需要精确结果 |
| 遗传算法 | 智能搜索，不遍历全部 | 参数空间大，可接受近似最优 |
| Walk-forward | 验证参数稳定性 | 避免过拟合，评估鲁棒性 |

## 1. 网格搜索（Grid Search）

### 基本用法

```python
from datetime import date
from aquant import BacktestConfig
from aquant.data.alds import ALDSDataSource
from aquant.optimization.grid_search import grid_search

# 定义参数网格
param_grid = {
    "fast_period": [5, 10, 15, 20],
    "slow_period": [20, 30, 40, 50],
}

# 回测配置
data_source = ALDSDataSource()
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
    show_progress=False,
)

# 执行网格搜索
results_df = grid_search(
    strategy_cls=MyStrategy,
    param_grid=param_grid,
    config=config,
    data_source=data_source,
    metric="sharpe",
)

# 查看最佳参数
best = results_df.sort("sharpe", descending=True).head(1)
print(best)
```

### 结果分析

```python
# 按夏普比率排序
top_10 = results_df.sort("sharpe", descending=True).head(10)
print(top_10.select(["fast_period", "slow_period", "sharpe", "total_return"]))

# 可视化参数与性能的关系
import matplotlib.pyplot as plt

# 绘制热力图
pivot = results_df.pivot(
    index="fast_period",
    columns="slow_period",
    values="sharpe",
)
plt.imshow(pivot, cmap="RdYlGn")
plt.colorbar(label="Sharpe Ratio")
plt.xlabel("Slow Period")
plt.ylabel("Fast Period")
plt.title("Parameter Grid Search Results")
plt.show()
```

## 2. 遗传算法（Genetic Algorithm）

遗传算法适合参数空间较大的场景，无需遍历所有组合。

### 基本用法

```python
from aquant.optimization.genetic_algorithm import GeneticAlgorithm

# 定义参数范围
param_ranges = {
    "fast_period": (5, 20, int),      # (最小值, 最大值, 类型)
    "slow_period": (20, 60, int),
    "threshold": (0.01, 0.1, float),
}

# 创建遗传算法优化器
ga = GeneticAlgorithm(
    strategy_class=MyStrategy,
    param_ranges=param_ranges,
    data_source=data_source,
    backtest_config=config,
    population_size=20,    # 种群大小
    generations=10,        # 迭代代数
    mutation_rate=0.1,     # 变异率
    crossover_rate=0.7,    # 交叉率
    scoring="sharpe",      # 优化目标
)

# 运行优化
best_params = ga.run(verbose=True)
print(f"最优参数: {best_params}")
print(f"最优得分: {ga.best_score():.4f}")
```

### 查看优化历史

```python
import matplotlib.pyplot as plt

# 绘制优化过程
generations = [h["generation"] for h in ga.history]
best_fitness = [h["best_fitness"] for h in ga.history]
avg_fitness = [h["avg_fitness"] for h in ga.history]

plt.plot(generations, best_fitness, label="Best")
plt.plot(generations, avg_fitness, label="Average")
plt.xlabel("Generation")
plt.ylabel("Fitness (Sharpe)")
plt.title("Genetic Algorithm Optimization")
plt.legend()
plt.grid(True)
plt.show()
```

## 3. Walk-Forward 分析

Walk-forward 分析用于验证参数的稳定性和策略的鲁棒性。

### 基本原理

1. **训练期**：在训练集上搜索最优参数
2. **测试期**：用训练得到的参数在测试集上回测
3. **滚动**：向前滚动时间窗口，重复上述过程

### 基本用法

```python
from aquant.optimization.walk_forward import walk_forward

# 执行 Walk-forward 分析
results_df = walk_forward(
    strategy_cls=MyStrategy,
    param_grid=param_grid,
    config=config,
    data_source=data_source,
    train_window=252,  # 训练期：252 个交易日（约 1 年）
    test_window=63,    # 测试期：63 个交易日（约 3 个月）
    metric="sharpe",
    n_jobs=1,          # 并行进程数（1 = 单进程）
)

# 查看每个折的结果
print(results_df.select([
    "fold_train_start",
    "fold_test_start",
    "fast_period",
    "slow_period",
    "sharpe",
    "total_return",
]))

# 计算平均表现
avg_sharpe = results_df["sharpe"].mean()
print(f"平均测试期夏普比率: {avg_sharpe:.4f}")

# 计算一致性（正收益率的比例）
consistency = (results_df["total_return"] > 0).mean()
print(f"一致性: {consistency * 100:.1f}%")
```

### 结果解读

- **平均测试期表现**：参数在样本外的真实表现
- **一致性**：策略在不同市场环境下的稳定性
- **训练 vs 测试差距**：过拟合程度（差距越大，过拟合越严重）

```python
# 对比训练期和测试期表现
# 注意：需要在 _run_fold 中记录训练期得分

train_test_gap = results_df["train_sharpe"] - results_df["test_sharpe"]
print(f"平均训练-测试差距: {train_test_gap.mean():.4f}")

# 差距过大说明过拟合
if train_test_gap.mean() > 0.5:
    print("警告：参数可能过拟合训练数据")
```

## 最佳实践

### 1. 参数范围选择

**不要过宽：**
```python
# ❌ 范围过宽，搜索时间长且可能找到无意义的极端值
param_grid = {
    "period": list(range(1, 200)),  # 1-200 天
}
```

**合理范围：**
```python
# ✅ 基于经验和理论选择合理范围
param_grid = {
    "period": [5, 10, 20, 30, 60],  # 常用周期
}
```

### 2. 避免过拟合

**使用 Walk-forward：**
```python
# 验证参数在样本外的表现
wf_results = walk_forward(
    strategy_cls=MyStrategy,
    param_grid=param_grid,
    config=config,
    data_source=data_source,
    train_window=252,
    test_window=63,
)

# 只有一致性高的参数才可靠
if (wf_results["total_return"] > 0).mean() > 0.7:
    print("参数通过 Walk-forward 验证")
```

**留出验证集：**
```python
# 训练集：2020-2022
train_config = BacktestConfig(
    start=date(2020, 1, 1),
    end=date(2022, 12, 31),
)

# 验证集：2023
test_config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
)

# 先在训练集上优化
train_results = grid_search(...)

# 再在验证集上测试最优参数
best_params = train_results.sort("sharpe", descending=True).row(0, named=True)
```

### 3. 多目标优化

不要只优化单一指标：

```python
# 综合考虑多个指标
def composite_score(row):
    sharpe = row["sharpe"]
    drawdown = row["max_drawdown"]
    return_pct = row["total_return"]

    # 综合得分：夏普 + 收益 - 回撤惩罚
    return sharpe + return_pct - abs(drawdown) * 2

results_df = results_df.with_columns(
    pl.struct(["sharpe", "max_drawdown", "total_return"])
    .map_elements(composite_score)
    .alias("composite_score")
)

best = results_df.sort("composite_score", descending=True).head(1)
```

### 4. 参数稳定性分析

```python
# 分析参数对性能的敏感度
import numpy as np

# 固定一个参数，变化另一个
fixed_slow = 30
sensitivity = results_df.filter(pl.col("slow_period") == fixed_slow)

plt.plot(sensitivity["fast_period"], sensitivity["sharpe"], marker="o")
plt.xlabel("Fast Period")
plt.ylabel("Sharpe Ratio")
plt.title(f"Sensitivity Analysis (slow_period={fixed_slow})")
plt.grid(True)
plt.show()
```

## 性能优化

### 并行网格搜索

```python
# Walk-forward 支持多进程
results = walk_forward(
    strategy_cls=MyStrategy,
    param_grid=param_grid,
    config=config,
    data_source=data_source,
    n_jobs=4,  # 使用 4 个进程
)
```

### 缩小搜索空间

```python
# 先粗搜索
coarse_grid = {
    "fast_period": [5, 15, 25],
    "slow_period": [20, 40, 60],
}

coarse_results = grid_search(...)
best_coarse = coarse_results.sort("sharpe", descending=True).head(1)

# 再细搜索
fine_grid = {
    "fast_period": list(range(best_coarse["fast_period"] - 2, best_coarse["fast_period"] + 3)),
    "slow_period": list(range(best_coarse["slow_period"] - 5, best_coarse["slow_period"] + 6)),
}

fine_results = grid_search(...)
```

## 常见问题

### Q: 网格搜索 vs 遗传算法，如何选择？

**网格搜索：**
- 参数少（2-3 个）
- 每个参数候选值少（< 10 个）
- 需要确保找到全局最优

**遗传算法：**
- 参数多（> 3 个）
- 参数空间大（候选值多或连续参数）
- 可以接受近似最优解

### Q: Walk-forward 需要多少个折？

建议至少 3-5 个折，覆盖不同市场环境：
- 牛市
- 熊市
- 震荡市

### Q: 如何判断参数是否过拟合？

1. Walk-forward 一致性低（< 60%）
2. 训练期表现远好于测试期（差距 > 50%）
3. 参数在不同时期差异很大
4. 参数取极端值（如周期 = 1 或 200）

## 下一步

- [策略开发指南](guide/strategy.md) - 开发可参数化的策略
- [性能优化指南](performance.md) - 加速参数搜索
