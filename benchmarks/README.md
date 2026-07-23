# 性能基准测试

本目录包含 aquant 框架的性能基准测试和分析工具。

## 工具列表

### 1. performance_benchmark.py

性能基准测试工具，测量回测引擎在不同场景下的性能。

**运行：**
```bash
uv run python benchmarks/performance_benchmark.py
```

**测试场景：**
- 单只股票，1 年回测
- 10 只股票，1 年回测
- 单只股票，3 年回测
- 高频调仓策略

**输出指标：**
- 耗时（秒）
- 交易日数
- 交易次数
- 速度（天/秒）
- 交易速度（笔/秒）

### 2. profile_engine.py

使用 cProfile 分析回测引擎的热点路径。

**运行：**
```bash
uv run python benchmarks/profile_engine.py
```

**输出：**
- 按累计时间排序的函数调用统计
- 按单次调用时间排序的函数调用统计
- 详细分析文件：`performance_profile.stats`

**可视化：**
```bash
uv run snakeviz performance_profile.stats
```

### 3. parallel_backtest.py

并行回测工具，支持多个策略同时运行并对比结果。

**运行：**
```bash
uv run python benchmarks/parallel_backtest.py
```

**功能：**
- 多策略并行回测
- 自动对比策略表现
- 按收益率排序输出结果

**自定义使用：**
```python
from benchmarks.parallel_backtest import run_parallel_backtest, StrategyConfig

strategy_configs = [
    StrategyConfig(name="策略A", strategy=strategy_a),
    StrategyConfig(name="策略B", strategy=strategy_b),
]

results = run_parallel_backtest(
    strategy_configs,
    backtest_config,
    max_workers=4,
)
```

## 性能优化建议

详见 [性能优化指南](../docs/performance.md)

## 典型性能指标

在标准硬件上（4 核 CPU，16GB 内存）：

| 场景 | 性能指标 |
|------|---------|
| 单只股票，1 年 | 500+ 天/秒 |
| 10 只股票，1 年 | 200+ 天/秒 |
| 单只股票，3 年 | 400+ 天/秒 |
| 高频调仓策略 | 100+ 笔/秒 |

## 性能优化流程

1. **建立基线**
   ```bash
   uv run python benchmarks/performance_benchmark.py
   ```

2. **识别瓶颈**
   ```bash
   uv run python benchmarks/profile_engine.py
   uv run snakeviz performance_profile.stats
   ```

3. **应用优化**
   - 参考性能优化指南
   - 实施具体优化措施

4. **验证效果**
   - 重新运行基准测试
   - 对比优化前后性能

## 常见优化方向

### 数据加载优化
- 使用数据缓存
- 预加载常用数据
- 批量加载减少 I/O

### 策略计算优化
- 缓存中间结果
- 避免重复计算
- 使用向量化计算

### 调仓优化
- 降低调仓频率
- 设置调仓阈值
- 控制股票池大小

### 并行化
- 多策略并行回测
- 参数优化并行化
- 合理设置 worker 数量
