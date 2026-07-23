# 策略下单模式对比分析

## 问题背景

当前 aquant 使用**信号-权重模式**：

```python
class Strategy:
    def on_bar(self, context: Context) -> list[Signal]:
        # 返回目标权重
        return [Signal(symbol="000001.SZ", weight=0.2)]
```

讨论：是否应该改为**主动下单模式**？

```python
class Strategy:
    def on_bar(self, context: Context, order_manager: OrderManager) -> None:
        # 策略主动下单
        order_manager.submit_order(symbol="000001.SZ", shares=1000, side="buy")
```

---

## 模式对比

### 模式 1：信号-权重（当前）

**特点**：

- 策略只表达**意图**（"我想持有 20% 的某标的"）
- 框架负责转换为**订单**（计算股数、分批买入）
- 框架负责**调仓逻辑**（replace vs incremental 模式）

**代码示例**：

```python
class MomentumStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        # 选出前 5 名
        top_stocks = self._rank_momentum(context.current_date)

        # 等权重分配
        weight = 1.0 / len(top_stocks)
        return [Signal(symbol=s, weight=weight) for s in top_stocks]

        # 框架自动清仓未出现的持仓（replace 模式）
```

**优点**：

1. ✅ **策略代码简洁**：不需要计算股数、不需要管理持仓差异
2. ✅ **声明式编程**：表达"想要什么"，而非"如何做"
3. ✅ **框架统一风控**：所有策略统一经过 Guard 检查
4. ✅ **适合选股策略**：A 股多因子、动量策略等主流场景
5. ✅ **回测与实盘一致**：实盘时可用相同的权重计算逻辑

**缺点**：

1. ❌ **表达能力受限**：难以实现"止损后不再买入"、"分批建仓"
2. ❌ **订单类型单一**：只支持市价单（开盘价成交）
3. ❌ **无法精细控制**：不能指定"买入 1000 股"或"卖出 50%"
4. ❌ **调仓逻辑固定**：replace/incremental 二选一，无法混合

---

### 模式 2：主动下单

**特点**：

- 策略直接**发出订单**（"买入 1000 股"）
- 策略负责**持仓管理**（自己跟踪仓位变化）
- 框架只负责**执行和结算**

**代码示例**：

```python
class AdvancedStrategy(Strategy):
    def __init__(self):
        self._stop_loss_triggered: set[str] = set()

    def on_bar(self, context: Context, order_manager: OrderManager) -> None:
        for symbol, pos in context.positions.items():
            # 止损逻辑：亏损 10% 卖出，且不再买入
            if (pos.market_value - pos.cost_basis * pos.shares) / (pos.cost_basis * pos.shares) < -0.1:
                order_manager.submit_order(symbol=symbol, shares=pos.shares, side="sell")
                self._stop_loss_triggered.add(symbol)

        # 选股
        top_stocks = self._rank_momentum(context.current_date)
        available_stocks = [s for s in top_stocks if s not in self._stop_loss_triggered]

        # 计算目标股数
        cash_per_stock = context.cash / len(available_stocks)
        for symbol in available_stocks:
            price = self._get_price(symbol, context.current_date)
            target_shares = int(cash_per_stock / price / 100) * 100
            current_shares = context.positions.get(symbol, PositionView(...)).shares
            delta = target_shares - current_shares

            if delta > 0:
                order_manager.submit_order(symbol=symbol, shares=delta, side="buy")
            elif delta < 0:
                order_manager.submit_order(symbol=symbol, shares=-delta, side="sell")
```

**优点**：

1. ✅ **表达能力强**：可实现任意复杂逻辑（止损、分批、条件单）
2. ✅ **订单类型丰富**：限价单、止损单、市价单（需框架支持）
3. ✅ **精细控制**：可指定精确股数、部分平仓
4. ✅ **接近实盘**：真实交易就是下单模式

**缺点**：

1. ❌ **策略代码复杂**：需要自己计算股数、管理持仓差异
2. ❌ **命令式编程**：关注"如何做"，而非"想要什么"
3. ❌ **风控分散**：每个策略需自己实现相似的风控逻辑
4. ❌ **容易出错**：计算股数、舍入、边界条件容易遗漏

---

## 深度对比

### 1. 代码复杂度

**信号-权重模式**（简洁）：

```python
# 15 行实现完整策略
class SimpleStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        scores = self._compute_scores(context.current_date)
        top_5 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
        return [Signal(symbol=s, weight=0.2) for s, _ in top_5]
```

**主动下单模式**（冗长）：

```python
# 50+ 行实现相同逻辑
class SimpleStrategy(Strategy):
    def on_bar(self, context: Context, order_manager: OrderManager) -> None:
        scores = self._compute_scores(context.current_date)
        top_5 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
        top_5_symbols = {s for s, _ in top_5}

        # 清仓不在 top_5 的持仓
        for symbol, pos in context.positions.items():
            if symbol not in top_5_symbols:
                order_manager.submit_order(symbol=symbol, shares=pos.shares, side="sell")

        # 计算目标股数
        target_value_per_stock = context.total_value * 0.2
        for symbol in top_5_symbols:
            price = self._get_price(symbol, context.current_date)
            target_shares = int(target_value_per_stock / price / 100) * 100
            current_shares = context.positions.get(symbol, PositionView(...)).shares
            delta = target_shares - current_shares

            if delta > 0:
                # 检查现金是否足够
                cost = delta * price * 1.0005  # 含滑点和佣金
                if context.cash >= cost:
                    order_manager.submit_order(symbol=symbol, shares=delta, side="buy")
            elif delta < 0:
                order_manager.submit_order(symbol=symbol, shares=-delta, side="sell")
```

**结论**：主动下单模式代码量增加 **3-4 倍**，且容易出错。

---

### 2. 表达能力

| 场景 | 信号-权重 | 主动下单 | 胜者 |
|------|-----------|----------|------|
| 等权重选股 | ✅ 简单 | ⚠️ 需计算 | 信号-权重 |
| 动态权重（风险平价） | ✅ 简单 | ⚠️ 需计算 | 信号-权重 |
| 止损后不再买入 | ❌ 难实现 | ✅ 容易 | 主动下单 |
| 分批建仓（3 天建完） | ❌ 无法实现 | ✅ 容易 | 主动下单 |
| 限价单（挂单等成交） | ❌ 不支持 | ✅ 支持 | 主动下单 |
| 条件单（跌破止损价卖出） | ❌ 不支持 | ✅ 支持 | 主动下单 |
| 配对交易（多空对冲） | ⚠️ 可用负权重 | ✅ 更清晰 | 平手 |

**结论**：

- **选股类策略**（A 股主流）：信号-权重完胜
- **复杂交易策略**（止损、分批、条件单）：主动下单必需

---

### 3. 真实案例

#### 案例 1：多因子选股策略（A 股主流）

**需求**：每月调仓，选出综合得分前 50 的股票，等权持有。

**信号-权重实现**（10 行）：

```python
class MultiFactorStrategy(Strategy):
    def on_bar(self, context: Context) -> list[Signal]:
        if context.current_date.day != 1:  # 每月 1 号调仓
            return []

        scores = self._compute_composite_score(context.current_date)
        top_50 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:50]
        return [Signal(symbol=s, weight=0.02) for s, _ in top_50]
```

**主动下单实现**（40+ 行）：

```python
class MultiFactorStrategy(Strategy):
    def on_bar(self, context: Context, order_manager: OrderManager) -> None:
        if context.current_date.day != 1:
            return

        scores = self._compute_composite_score(context.current_date)
        top_50 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:50]
        top_50_symbols = {s for s, _ in top_50}

        # 清仓不在 top_50 的持仓
        for symbol in list(context.positions.keys()):
            if symbol not in top_50_symbols:
                order_manager.submit_order(
                    symbol=symbol,
                    shares=context.positions[symbol].shares,
                    side="sell"
                )

        # 等待卖单结算后再计算可用现金（实际需要异步处理，更复杂）
        # ...（此处省略 20 行现金管理逻辑）

        # 买入 top_50
        target_value = context.total_value * 0.02
        for symbol in top_50_symbols:
            price = self._get_price(symbol, context.current_date)
            target_shares = int(target_value / price / 100) * 100
            current_shares = context.positions.get(symbol, ...).shares
            delta = target_shares - current_shares
            if delta > 0:
                order_manager.submit_order(symbol=symbol, shares=delta, side="buy")
```

**结论**：选股策略用信号-权重模式效率高 **4 倍**。

---

#### 案例 2：趋势追踪 + 止损策略

**需求**：

- 趋势向上时买入
- 亏损 10% 止损，且后续不再买入该标的
- 盈利 20% 止盈

**信号-权重实现**（❌ 无法实现）：

```python
# 无法表达"止损后不再买入"
# 无法表达"止盈"（需要记录成本价，但 Context 只有 market_value）
```

**主动下单实现**（✅ 可实现）：

```python
class TrendFollowStrategy(Strategy):
    def __init__(self):
        self._blacklist: set[str] = set()  # 止损黑名单

    def on_bar(self, context: Context, order_manager: OrderManager) -> None:
        # 止损 / 止盈
        for symbol, pos in context.positions.items():
            pnl_ratio = (pos.market_value - pos.cost_basis * pos.shares) / (pos.cost_basis * pos.shares)
            if pnl_ratio < -0.1:  # 止损
                order_manager.submit_order(symbol=symbol, shares=pos.shares, side="sell")
                self._blacklist.add(symbol)
            elif pnl_ratio > 0.2:  # 止盈
                order_manager.submit_order(symbol=symbol, shares=pos.shares, side="sell")

        # 趋势判断 + 买入
        trending_up = self._find_trending_stocks(context.current_date)
        for symbol in trending_up:
            if symbol in self._blacklist:
                continue
            if symbol not in context.positions:
                # 买入逻辑
                ...
```

**结论**：止损/止盈策略必须用主动下单模式。

---

## 最佳实践建议

### 方案 A：双模式共存（推荐）

**设计**：

```python
class Strategy(ABC):
    mode: Literal["signal", "order"] = "signal"  # 默认信号模式

    # 信号模式（适合选股）
    def on_bar(self, context: Context) -> list[Signal]:
        return []

    # 下单模式（适合复杂策略）
    def on_bar_order(self, context: Context, order_manager: OrderManager) -> None:
        pass

class Engine:
    def run(self):
        if self._strategy.mode == "signal":
            signals = self._strategy.on_bar(context)
            self._matcher.execute(signals, ...)
        else:
            order_manager = OrderManager(self._portfolio, self._matcher)
            self._strategy.on_bar_order(context, order_manager)
```

**优点**：

- ✅ 简单策略用信号模式（当前 90% 场景）
- ✅ 复杂策略用下单模式（止损、分批、限价单）
- ✅ 向后兼容（默认信号模式）

**缺点**：

- ⚠️ API 增加复杂度
- ⚠️ 用户需要选择模式

---

### 方案 B：仅保留信号模式 + 扩展表达能力（推荐）

**设计**：增强 `Signal` 的表达能力

```python
@dataclass
class Signal:
    symbol: str
    weight: float  # 仍支持权重模式（向后兼容）

    # 新增：精确控制
    target_shares: int | None = None  # 精确指定股数（优先于 weight）
    side: Literal["buy", "sell", "auto"] = "auto"  # auto = 框架自动判断

    # 新增：高级订单
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = None
    stop_price: float | None = None

    # 新增：元数据
    tags: set[str] = field(default_factory=set)  # {"stop_loss", "take_profit"}
    reason: str = ""  # 下单原因（便于分析）

# 简单策略：仍用 weight
Signal(symbol="000001.SZ", weight=0.2)

# 复杂策略：用 target_shares + tags
Signal(
    symbol="000001.SZ",
    target_shares=0,  # 清仓
    side="sell",
    tags={"stop_loss"},
    reason="跌破止损价"
)

# 限价单
Signal(
    symbol="000001.SZ",
    weight=0.1,
    order_type="limit",
    limit_price=10.5,
    reason="回调买入"
)
```

**优点**：

- ✅ 向后兼容（weight 仍然有效）
- ✅ 表达能力增强（支持精确股数、限价单、止损单）
- ✅ API 统一（只有一个 `on_bar`）
- ✅ 保留声明式风格

**缺点**：

- ⚠️ 仍无法实现"止损后永不买入"（需要策略自己记录状态）

---

### 方案 C：混合模式（最灵活但复杂）

**设计**：信号模式 + 事件订阅实现复杂逻辑

```python
class TrendFollowStrategy(Strategy):
    def __init__(self):
        self._blacklist: set[str] = set()

    def setup_subscriptions(self, bus: MessageBus) -> None:
        # 订阅订单成交事件
        bus.subscribe("order.filled", self._on_order_filled)

    def _on_order_filled(self, event: OrderFilledEvent) -> None:
        # 如果是止损卖出，加入黑名单
        if event.side == "sell" and "止损" in event.meta.get("reason", ""):
            self._blacklist.add(event.symbol)

    def on_bar(self, context: Context) -> list[Signal]:
        signals = []

        # 止损检查
        for symbol, pos in context.positions.items():
            if (pos.market_value - pos.cost_basis * pos.shares) / (pos.cost_basis * pos.shares) < -0.1:
                signals.append(Signal(
                    symbol=symbol,
                    weight=0,
                    meta={"reason": "止损"}
                ))

        # 趋势买入
        trending = self._find_trending_stocks(context.current_date)
        for symbol in trending:
            if symbol not in self._blacklist:  # 过滤黑名单
                signals.append(Signal(symbol=symbol, weight=0.1))

        return signals
```

**优点**：

- ✅ 保留信号模式的简洁性
- ✅ 通过事件订阅实现复杂状态管理
- ✅ 充分利用已有的消息总线

**缺点**：

- ⚠️ 需要理解事件驱动编程
- ⚠️ 调试稍复杂（异步逻辑）

---

## 最终推荐

### 短期（当前版本）：保持信号-权重模式

**理由**：

1. ✅ 覆盖 90% 的 A 股策略场景（选股、轮动、配置）
2. ✅ 代码简洁，学习曲线平缓
3. ✅ 与业界主流框架一致（Backtrader、Zipline 都是信号模式）

**补充**：在文档中说明限制：

- 适合选股类策略
- 不适合止损/止盈等需要精细控制的策略
- 高级需求可通过事件订阅 + 元数据实现

---

### 中期（1-2 月）：方案 B - 扩展 Signal 表达能力

**实施**：

1. 新增 `target_shares`、`order_type`、`tags` 字段
2. 保持 `weight` 向后兼容
3. 文档中提供"从权重到精确股数"的迁移指南

**覆盖场景**：

- ✅ 简单选股：`Signal(symbol, weight=0.2)`
- ✅ 精确控制：`Signal(symbol, target_shares=1000)`
- ✅ 限价单：`Signal(symbol, weight=0.1, order_type="limit", limit_price=10.5)`
- ⚠️ 止损黑名单：需要策略自己管理状态（通过事件订阅）

---

### 长期（6 月+）：方案 A - 双模式共存

**实施**：

1. 保留信号模式作为默认
2. 新增下单模式 `on_bar_order(context, order_manager)`
3. 策略通过 `mode` 属性选择

**适用场景**：

- 信号模式：选股、轮动、配置（90%）
- 下单模式：高频、做市、复杂止损/止盈（10%）

---

## 总结表

| 维度 | 信号-权重（当前） | 主动下单 | 推荐 |
|------|------------------|----------|------|
| **代码复杂度** | ⭐⭐⭐⭐⭐（简洁） | ⭐⭐（冗长） | 信号-权重 |
| **学习曲线** | ⭐⭐⭐⭐⭐（平缓） | ⭐⭐⭐（陡峭） | 信号-权重 |
| **表达能力** | ⭐⭐⭐（中等） | ⭐⭐⭐⭐⭐（强） | 看场景 |
| **A 股选股策略** | ⭐⭐⭐⭐⭐（完美） | ⭐⭐（过度设计） | 信号-权重 |
| **止损/止盈策略** | ⭐⭐（困难） | ⭐⭐⭐⭐⭐（容易） | 主动下单 |
| **限价单/条件单** | ⭐（不支持） | ⭐⭐⭐⭐⭐（支持） | 主动下单 |
| **实盘一致性** | ⭐⭐⭐⭐（高） | ⭐⭐⭐⭐⭐（完全） | 主动下单 |

**最终建议**：

1. **短期**：保持信号-权重模式（覆盖 90% 场景）
2. **中期**：扩展 Signal 表达能力（支持 target_shares、order_type）
3. **长期**：双模式共存（让用户选择）

当前架构选择是正确的，不需要立即改为主动下单模式。
