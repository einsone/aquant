# 实盘交易

本文介绍如何将回测策略部署到实盘交易。

## 实盘交易架构

aquant 通过 `BrokerAdapter` 抽象层支持实盘交易：

```text
策略 → 信号 → 风控 → BrokerAdapter → 券商接口 → 真实市场
```

**关键区别：**

- **回测**：使用 `SimulatedBroker` 模拟撮合
- **实盘**：使用实际券商的 `BrokerAdapter` 执行订单

## BrokerAdapter 接口

所有券商适配器都需要实现 `BrokerAdapter` 接口：

```python
from aquant.broker.adapter import BrokerAdapter
from datetime import datetime

class MyBrokerAdapter(BrokerAdapter):
    def get_cash(self) -> float:
        """查询可用资金"""
        pass

    def get_position(self, symbol: str) -> int:
        """查询持仓数量"""
        pass

    def buy(self, symbol: str, shares: int, price: float | None = None) -> str:
        """买入股票

        Args:
            symbol: 股票代码
            shares: 股数
            price: 限价（None 表示市价）

        Returns:
            订单 ID
        """
        pass

    def sell(self, symbol: str, shares: int, price: float | None = None) -> str:
        """卖出股票"""
        pass

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        pass

    def get_order_status(self, order_id: str) -> dict:
        """查询订单状态"""
        pass
```

## 模拟券商（用于测试）

aquant 内置 `SimulatedBroker` 用于实盘前测试：

```python
from aquant.broker.simulated import SimulatedBroker
from datetime import date

# 创建模拟券商
broker = SimulatedBroker(
    initial_capital=1_000_000.0,
    commission_rate=0.0003,
    stamp_duty_rate=0.001,
)

# 测试交易
order_id = broker.buy(symbol="000001.SZ", shares=100, price=10.0)
print(f"订单 ID: {order_id}")

# 查询持仓
position = broker.get_position("000001.SZ")
print(f"持仓: {position} 股")

# 查询资金
cash = broker.get_cash()
print(f"可用资金: {cash:,.2f} 元")
```

## 实盘交易示例

### 基础实盘交易

```python
from datetime import date, datetime, time
from aquant import Strategy, Signal, Context, Engine, BacktestConfig
from aquant.broker.adapter import BrokerAdapter
from aquant.data.alds import ALDSDataSource
import time as time_module

class LiveTradingEngine:
    """实盘交易引擎"""

    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerAdapter,
        data_source: ALDSDataSource,
        trading_time: time = time(14, 30),  # 每天 14:30 交易
    ):
        self.strategy = strategy
        self.broker = broker
        self.data_source = data_source
        self.trading_time = trading_time

    def run(self):
        """运行实盘交易"""
        print("实盘交易引擎启动")

        while True:
            now = datetime.now()

            # 判断是否为交易时间
            if self._is_trading_time(now):
                self._execute_trading()
                # 等待到明天
                time_module.sleep(86400)
            else:
                # 每分钟检查一次
                time_module.sleep(60)

    def _is_trading_time(self, now: datetime) -> bool:
        """判断是否为交易时间"""
        # 检查是否为工作日
        if now.weekday() >= 5:  # 周六日
            return False

        # 检查时间
        current_time = now.time()
        return current_time.hour == self.trading_time.hour and \
               current_time.minute == self.trading_time.minute

    def _execute_trading(self):
        """执行交易"""
        print(f"开始执行交易: {datetime.now()}")

        try:
            # 构建上下文
            context = self._build_context()

            # 调用策略生成信号
            signals = self.strategy.on_bar(context)

            # 执行交易
            self._execute_signals(signals, context)

            print("交易执行完成")

        except Exception as e:
            print(f"交易执行失败: {e}")

    def _build_context(self) -> Context:
        """构建策略上下文"""
        # 实现上下文构建逻辑
        # 需要提供查询接口，从 broker 获取持仓信息
        pass

    def _execute_signals(self, signals: list[Signal], context: Context):
        """执行信号"""
        total_value = self.broker.get_cash()

        # 计算当前持仓市值
        for symbol in self._get_all_symbols():
            position = self.broker.get_position(symbol)
            if position > 0:
                # 获取当前价格
                bars = self.data_source.load_bars(date.today(), {symbol})
                if symbol in bars:
                    total_value += position * bars[symbol].close

        # 执行调仓
        target_positions = {}
        for signal in signals:
            target_value = total_value * signal.weight
            bars = self.data_source.load_bars(date.today(), {signal.symbol})
            if signal.symbol in bars:
                target_shares = int(target_value / bars[signal.symbol].close)
                target_positions[signal.symbol] = target_shares

        # 下单
        for symbol, target_shares in target_positions.items():
            current_shares = self.broker.get_position(symbol)
            delta = target_shares - current_shares

            if delta > 0:
                # 买入
                self.broker.buy(symbol=symbol, shares=delta)
                print(f"买入 {symbol}: {delta} 股")
            elif delta < 0:
                # 卖出
                self.broker.sell(symbol=symbol, shares=-delta)
                print(f"卖出 {symbol}: {-delta} 股")

    def _get_all_symbols(self) -> list[str]:
        """获取所有股票代码"""
        # 返回策略关注的股票池
        return []

# 使用示例
strategy = MyStrategy()
broker = MyBrokerAdapter()  # 实际券商适配器
data_source = ALDSDataSource()

engine = LiveTradingEngine(strategy, broker, data_source)
engine.run()
```

### 带风控的实盘交易

```python
from aquant.risk.guard import RiskGuard

class SafeLiveTradingEngine(LiveTradingEngine):
    """带风控的实盘交易引擎"""

    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerAdapter,
        data_source: ALDSDataSource,
        risk_guards: list[RiskGuard] = None,
        max_daily_loss: float = 0.03,  # 日最大亏损 3%
    ):
        super().__init__(strategy, broker, data_source)
        self.risk_guards = risk_guards or []
        self.max_daily_loss = max_daily_loss
        self.daily_start_value = 0.0

    def _execute_trading(self):
        """执行交易（带风控检查）"""
        # 记录日初资产
        if self.daily_start_value == 0:
            self.daily_start_value = self._get_total_value()

        # 检查日内亏损
        current_value = self._get_total_value()
        daily_loss = (self.daily_start_value - current_value) / self.daily_start_value

        if daily_loss > self.max_daily_loss:
            print(f"触发日最大亏损限制: {daily_loss * 100:.2f}%")
            return

        # 执行正常交易流程
        super()._execute_trading()

    def _get_total_value(self) -> float:
        """计算总资产"""
        total = self.broker.get_cash()

        for symbol in self._get_all_symbols():
            position = self.broker.get_position(symbol)
            if position > 0:
                bars = self.data_source.load_bars(date.today(), {symbol})
                if symbol in bars:
                    total += position * bars[symbol].close

        return total
```

## 券商适配器示例

### 示例：东方财富适配器

```python
from aquant.broker.adapter import BrokerAdapter
import requests

class EastMoneyAdapter(BrokerAdapter):
    """东方财富券商适配器（示例）"""

    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password
        self.session = self._login()

    def _login(self) -> requests.Session:
        """登录券商系统"""
        session = requests.Session()
        # 实现登录逻辑
        # response = session.post("https://api.eastmoney.com/login", ...)
        return session

    def get_cash(self) -> float:
        """查询可用资金"""
        response = self.session.get("https://api.eastmoney.com/account/cash")
        data = response.json()
        return data["available_cash"]

    def get_position(self, symbol: str) -> int:
        """查询持仓数量"""
        response = self.session.get(
            "https://api.eastmoney.com/account/positions",
            params={"symbol": symbol}
        )
        data = response.json()
        return data.get("shares", 0)

    def buy(self, symbol: str, shares: int, price: float | None = None) -> str:
        """买入股票"""
        order_data = {
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "side": "buy",
        }
        response = self.session.post(
            "https://api.eastmoney.com/trade/order",
            json=order_data
        )
        data = response.json()
        return data["order_id"]

    def sell(self, symbol: str, shares: int, price: float | None = None) -> str:
        """卖出股票"""
        order_data = {
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "side": "sell",
        }
        response = self.session.post(
            "https://api.eastmoney.com/trade/order",
            json=order_data
        )
        data = response.json()
        return data["order_id"]

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        response = self.session.post(
            f"https://api.eastmoney.com/trade/order/{order_id}/cancel"
        )
        return response.status_code == 200

    def get_order_status(self, order_id: str) -> dict:
        """查询订单状态"""
        response = self.session.get(
            f"https://api.eastmoney.com/trade/order/{order_id}"
        )
        return response.json()
```

## 实盘注意事项

### 1. 回测与实盘差异

#### 滑点

```python
# 回测中的理论价格
backtest_price = bar.close

# 实盘中的实际成交价格可能偏离
actual_price = bar.close * (1 + slippage)
```

#### 成交延迟

```python
# 回测：信号立即成交
# 实盘：订单提交后需要等待撮合

# 解决方案：使用限价单 + 订单监控
order_id = broker.buy(symbol, shares, price=limit_price)
time.sleep(1)
status = broker.get_order_status(order_id)
if status["filled"] < shares:
    # 部分成交或未成交，需要调整策略
    pass
```

#### 交易限制

```python
# 回测：可以随意交易
# 实盘：
# - T+1 限制（A 股当天买入不能卖出）
# - 涨跌停限制（无法在涨停价买入、跌停价卖出）
# - 交易时间限制（9:30-11:30, 13:00-15:00）
```

### 2. 订单管理

```python
class OrderManager:
    """订单管理器"""

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self.pending_orders = {}

    def submit_order(self, symbol: str, side: str, shares: int, price: float = None) -> str:
        """提交订单"""
        if side == "buy":
            order_id = self.broker.buy(symbol, shares, price)
        else:
            order_id = self.broker.sell(symbol, shares, price)

        self.pending_orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "shares": shares,
            "price": price,
            "status": "pending",
        }

        return order_id

    def check_orders(self):
        """检查订单状态"""
        for order_id in list(self.pending_orders.keys()):
            status = self.broker.get_order_status(order_id)

            if status["status"] == "filled":
                # 订单已成交
                print(f"订单 {order_id} 已成交")
                del self.pending_orders[order_id]

            elif status["status"] == "cancelled":
                # 订单已撤销
                print(f"订单 {order_id} 已撤销")
                del self.pending_orders[order_id]

            elif status["status"] == "partial_filled":
                # 部分成交
                print(f"订单 {order_id} 部分成交: {status['filled']}/{status['total']}")

    def cancel_all_pending(self):
        """撤销所有未成交订单"""
        for order_id in list(self.pending_orders.keys()):
            self.broker.cancel_order(order_id)
            del self.pending_orders[order_id]
```

### 3. 异常处理

```python
class RobustLiveTradingEngine(LiveTradingEngine):
    """健壮的实盘交易引擎"""

    def _execute_trading(self):
        """执行交易（带异常处理）"""
        try:
            super()._execute_trading()

        except ConnectionError as e:
            # 网络连接错误
            print(f"网络连接失败: {e}")
            self._send_alert("网络连接失败")

        except Exception as e:
            # 其他错误
            print(f"交易执行异常: {e}")
            self._send_alert(f"交易异常: {e}")

            # 紧急清仓（可选）
            if self._is_critical_error(e):
                self._emergency_liquidate()

    def _send_alert(self, message: str):
        """发送告警"""
        # 发送邮件、短信、钉钉等
        print(f"[告警] {message}")

    def _is_critical_error(self, error: Exception) -> bool:
        """判断是否为严重错误"""
        # 根据错误类型判断
        return False

    def _emergency_liquidate(self):
        """紧急清仓"""
        print("执行紧急清仓")
        for symbol in self._get_all_symbols():
            position = self.broker.get_position(symbol)
            if position > 0:
                self.broker.sell(symbol, position)
```

### 4. 日志记录

```python
import structlog
from datetime import datetime

logger = structlog.get_logger()

class LoggedLiveTradingEngine(LiveTradingEngine):
    """带日志的实盘交易引擎"""

    def _execute_trading(self):
        """执行交易（带日志）"""
        logger.info("开始交易", timestamp=datetime.now())

        # 记录账户状态
        cash = self.broker.get_cash()
        total_value = self._get_total_value()

        logger.info(
            "账户状态",
            cash=f"{cash:,.2f}",
            total_value=f"{total_value:,.2f}",
        )

        # 执行交易
        super()._execute_trading()

        # 记录交易结果
        new_total_value = self._get_total_value()
        pnl = new_total_value - total_value

        logger.info(
            "交易完成",
            pnl=f"{pnl:,.2f}",
            pnl_pct=f"{pnl / total_value * 100:.2f}%",
        )
```

## 从回测到实盘的迁移

### 1. 回测验证

```python
# 第一步：在历史数据上回测
config = BacktestConfig(
    start=date(2023, 1, 1),
    end=date(2023, 12, 31),
    initial_capital=1_000_000.0,
)

engine = Engine(strategy, data_source, config)
result = engine.run()

print(f"回测收益率: {result.metrics['total_return'] * 100:.2f}%")
print(f"夏普比率: {result.metrics['sharpe']:.2f}")
print(f"最大回撤: {result.metrics['max_drawdown'] * 100:.2f}%")
```

### 2. 模拟盘测试

```python
# 第二步：使用模拟券商测试实盘逻辑
from aquant.broker.simulated import SimulatedBroker

broker = SimulatedBroker(initial_capital=100_000.0)
engine = LiveTradingEngine(strategy, broker, data_source)

# 运行一段时间（如 1 个月）
# 验证实盘逻辑正确性
```

### 3. 小资金实盘

```python
# 第三步：用小资金实盘验证
broker = RealBrokerAdapter(account="...", password="...")
engine = SafeLiveTradingEngine(
    strategy,
    broker,
    data_source,
    max_daily_loss=0.02,  # 严格风控
)

# 运行 1-3 个月，观察实际表现
```

### 4. 全额实盘

```python
# 第四步：确认无误后投入全额资金
engine = SafeLiveTradingEngine(
    strategy,
    broker,
    data_source,
    max_daily_loss=0.03,
)

engine.run()
```

## 实盘监控

### 监控指标

```python
class PerformanceMonitor:
    """实盘绩效监控"""

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self.initial_value = 0.0
        self.peak_value = 0.0

    def update(self):
        """更新监控指标"""
        current_value = self._get_total_value()

        if self.initial_value == 0:
            self.initial_value = current_value
            self.peak_value = current_value

        if current_value > self.peak_value:
            self.peak_value = current_value

        # 计算指标
        total_return = (current_value - self.initial_value) / self.initial_value
        drawdown = (self.peak_value - current_value) / self.peak_value

        logger.info(
            "实盘监控",
            current_value=f"{current_value:,.2f}",
            total_return=f"{total_return * 100:.2f}%",
            drawdown=f"{drawdown * 100:.2f}%",
        )

        # 告警检查
        if drawdown > 0.10:
            self._send_alert(f"回撤达到 {drawdown * 100:.2f}%")

    def _get_total_value(self) -> float:
        """计算总资产"""
        # 实现逻辑
        return 0.0

    def _send_alert(self, message: str):
        """发送告警"""
        print(f"[告警] {message}")
```

## 最佳实践

### 1. 渐进式上线

- 先回测 → 再模拟盘 → 小资金实盘 → 全额实盘
- 每个阶段充分验证后再进入下一阶段

### 2. 严格风控

- 设置日最大亏损限制
- 设置单笔订单最大金额
- 异常情况自动清仓

### 3. 完善监控

- 实时监控账户状态
- 异常情况及时告警
- 记录完整的交易日志

### 4. 定期复盘

- 每周/每月复盘策略表现
- 对比回测与实盘差异
- 根据市场变化调整参数

## 下一步

- [策略开发](strategy.md) - 优化策略逻辑
- [风控管理](risk-management.md) - 加强实盘风控
- [数据源接入](data-source.md) - 接入实时数据源
