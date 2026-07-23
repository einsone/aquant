# 实盘交易指南

Aquant 提供了实盘交易功能，帮助你将回测验证过的策略部署到真实市场。

⚠️ **风险提示**：实盘交易涉及真实资金，请务必在充分测试后再使用，建议从小资金开始。

## 架构概览

实盘交易系统包含以下核心组件：

1. **订单管理器** (OrderManager) - 订单生命周期管理
2. **告警系统** (AlertManager) - 多渠道实时告警
3. **实盘引擎** (LiveEngine) - 交易调度和执行
4. **券商适配器** (BrokerAdapter) - 券商接口封装

## 快速开始

### 1. 创建券商适配器

首先需要实现券商适配器接口：

```python
from aquant.broker.adapter import BrokerAdapter

class MyBrokerAdapter(BrokerAdapter):
    """自定义券商适配器"""
    
    def __init__(self, account_id: str, api_key: str):
        self.account_id = account_id
        self.api_key = api_key
        # 初始化券商 API 连接
        
    def buy(self, symbol: str, shares: int, price: float | None = None) -> str:
        """买入股票，返回订单ID"""
        # 调用券商 API 下单
        order_id = self._call_broker_api(...)
        return order_id
        
    def sell(self, symbol: str, shares: int, price: float | None = None) -> str:
        """卖出股票，返回订单ID"""
        order_id = self._call_broker_api(...)
        return order_id
        
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        success = self._call_broker_api(...)
        return success
        
    def get_order_status(self, order_id: str) -> dict:
        """查询订单状态"""
        status = self._call_broker_api(...)
        return {
            "status": "filled",  # filled, partial_filled, cancelled, rejected
            "filled_shares": 100,
            "avg_price": 10.5
        }
        
    def get_position(self, symbol: str) -> dict | None:
        """查询持仓"""
        position = self._call_broker_api(...)
        return {
            "symbol": symbol,
            "shares": 1000,
            "cost_basis": 10.2,
            "market_value": 10500.0
        }
```

### 2. 配置订单管理器

```python
from aquant.live.order_manager import OrderManager

# 创建券商适配器
broker = MyBrokerAdapter(
    account_id="your_account",
    api_key="your_api_key"
)

# 创建订单管理器
order_mgr = OrderManager(broker)

# 提交订单
order = order_mgr.submit_order(
    symbol="000001.SZ",
    side="buy",
    shares=100,
    price=10.5  # None 表示市价单
)

print(f"订单已提交: {order.order_id}")
```

### 3. 配置告警系统

```python
from aquant.live.alerts import (
    AlertManager,
    EmailAlertChannel,
    DingTalkAlertChannel,
    WeChatWorkAlertChannel
)

# 创建告警管理器
alert_mgr = AlertManager()

# 添加邮件告警
email_channel = EmailAlertChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your_email@gmail.com",
    password="your_password",
    from_addr="your_email@gmail.com",
    to_addrs=["recipient@example.com"]
)
alert_mgr.add_channel(email_channel)

# 添加钉钉告警
dingtalk_channel = DingTalkAlertChannel(
    webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
    secret="SECxxxx"  # 可选，用于签名验证
)
alert_mgr.add_channel(dingtalk_channel)

# 发送告警
alert_mgr.info("策略启动", "动量策略已成功启动")
alert_mgr.warning("信号生成", "检测到买入信号：000001.SZ")
alert_mgr.error("订单失败", "订单 #123 提交失败", {"reason": "资金不足"})
```

### 4. 运行实盘交易

```python
from datetime import time
from aquant.live.engine import LiveEngine
from aquant.live.order_manager import OrderManager
from aquant.live.alerts import AlertManager
from my_strategy import MyStrategy

# 1. 创建组件
broker = MyBrokerAdapter(...)
order_mgr = OrderManager(broker)
alert_mgr = AlertManager()
# ... 配置告警渠道 ...

# 2. 创建策略
data_source = MyDataSource()
strategy = MyStrategy(data_source)

# 3. 创建实盘引擎
live_engine = LiveEngine(
    strategy=strategy,
    data_source=data_source,
    order_manager=order_mgr,
    alert_manager=alert_mgr,
    
    # 交易时间配置
    market_open=time(9, 30),
    market_close=time(15, 0),
    
    # 风控配置
    max_position_value=500000,  # 单个持仓最大市值
    max_daily_loss=10000,       # 日最大亏损
    
    # 止损配置
    stop_loss_pct=0.05,  # 5% 止损
)

# 4. 启动实盘交易
live_engine.start()
```

## 订单管理

### 订单状态

订单在生命周期中有以下状态：

- `PENDING` - 待提交
- `SUBMITTED` - 已提交
- `PARTIAL_FILLED` - 部分成交
- `FILLED` - 完全成交
- `CANCELLED` - 已撤销
- `REJECTED` - 被拒绝
- `FAILED` - 提交失败

### 订单查询

```python
# 获取特定订单
order = order_mgr.get_order("order_123")
print(f"状态: {order.status}")
print(f"成交数量: {order.filled_shares}/{order.shares}")
print(f"成交均价: {order.avg_fill_price}")

# 获取所有未完成订单
pending_orders = order_mgr.get_pending_orders()
for order in pending_orders:
    print(f"{order.symbol}: {order.shares} 股 @ {order.price}")

# 获取已成交订单
filled_orders = order_mgr.get_filled_orders()
```

### 订单撤销

```python
# 撤销单个订单
success = order_mgr.cancel_order("order_123")

# 批量撤销所有未完成订单
count = order_mgr.cancel_all_pending()
print(f"已撤销 {count} 个订单")
```

### 订单状态检查

```python
# 检查所有订单状态
statuses = order_mgr.check_orders()

for order_id, status in statuses.items():
    print(f"订单 {order_id}: {status}")
```

### 订单统计

```python
# 获取订单统计
summary = order_mgr.summary()

print(f"总订单数: {summary['total']}")
print(f"已成交: {summary['filled']}")
print(f"待成交: {summary['pending']}")
print(f"已撤销: {summary['cancelled']}")
print(f"成交率: {summary['fill_rate']:.2%}")
```

## 告警系统

### 告警级别

- `INFO` - 信息（如策略启动、信号生成）
- `WARNING` - 警告（如接近风控阈值）
- `ERROR` - 错误（如订单失败）
- `CRITICAL` - 严重（如触发止损、超过风控限制）

### 多渠道告警

#### 邮件告警

```python
from aquant.live.alerts import EmailAlertChannel

email = EmailAlertChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="bot@example.com",
    password="your_password",
    from_addr="bot@example.com",
    to_addrs=["trader@example.com", "risk@example.com"]
)

alert_mgr.add_channel(email)
```

#### 钉钉告警

```python
from aquant.live.alerts import DingTalkAlertChannel

dingtalk = DingTalkAlertChannel(
    webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
    secret="SECxxxx"  # 启用签名验证（推荐）
)

alert_mgr.add_channel(dingtalk)
```

#### 企业微信告警

```python
from aquant.live.alerts import WeChatWorkAlertChannel

wechat = WeChatWorkAlertChannel(
    webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
)

alert_mgr.add_channel(wechat)
```

### 告警示例

```python
# 策略启动
alert_mgr.info("策略启动", "动量策略已启动，初始资金 100万")

# 信号告警
alert_mgr.warning(
    "买入信号",
    "检测到买入信号",
    extra={"symbol": "000001.SZ", "price": 10.5, "shares": 1000}
)

# 订单告警
alert_mgr.info(
    "订单成交",
    "买入订单已成交",
    extra={"order_id": "123", "symbol": "000001.SZ", "shares": 1000}
)

# 风控告警
alert_mgr.error(
    "触发止损",
    "持仓亏损超过 5%，已触发止损",
    extra={"symbol": "000001.SZ", "loss": -5000}
)

# 严重错误
alert_mgr.critical(
    "系统异常",
    "数据源连接失败，策略已暂停",
    extra={"error": str(e)}
)
```

## 风险控制

### 仓位限制

```python
# 在策略中实现风控
class MyStrategy(Strategy):
    def __init__(self, data_source, max_position=0.2):
        self.data_source = data_source
        self.max_position = max_position  # 单个持仓不超过 20%
        
    def on_bar(self, context):
        # 计算目标仓位
        signals = self._generate_signals(context)
        
        # 风控：限制单个持仓
        for signal in signals:
            if signal.weight > self.max_position:
                signal.weight = self.max_position
                
        return signals
```

### 止损止盈

```python
class StopLossStrategy(Strategy):
    def __init__(self, data_source, stop_loss=0.05, take_profit=0.10):
        self.data_source = data_source
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.entry_prices = {}
        
    def on_bar(self, context):
        signals = []
        
        # 检查持仓止损止盈
        for symbol, position in context.positions.items():
            entry_price = self.entry_prices.get(symbol, position.cost_basis)
            current_price = context.current_bars[symbol].close
            
            ret = (current_price - entry_price) / entry_price
            
            # 止损
            if ret <= -self.stop_loss:
                signals.append(Signal(symbol=symbol, weight=0))
                alert_mgr.warning("触发止损", f"{symbol} 亏损 {ret:.2%}")
                
            # 止盈
            elif ret >= self.take_profit:
                signals.append(Signal(symbol=symbol, weight=0))
                alert_mgr.info("触发止盈", f"{symbol} 盈利 {ret:.2%}")
                
        return signals
```

### 日亏损限制

```python
class DailyLossLimit:
    def __init__(self, max_daily_loss=10000):
        self.max_daily_loss = max_daily_loss
        self.daily_pnl = 0
        self.today = None
        
    def check(self, current_date, current_pnl):
        # 重置日计数
        if self.today != current_date:
            self.today = current_date
            self.daily_pnl = 0
            
        self.daily_pnl = current_pnl
        
        # 检查是否超限
        if self.daily_pnl <= -self.max_daily_loss:
            alert_mgr.critical(
                "日亏损超限",
                f"今日亏损 {self.daily_pnl:.2f}，已暂停交易"
            )
            return False
            
        return True
```

## 监控和日志

### 日志配置

```python
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('live_trading.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 在策略中使用
class MyStrategy(Strategy):
    def on_bar(self, context):
        logger.info(f"处理 {context.current_date} 的数据")
        
        signals = self._generate_signals(context)
        
        for signal in signals:
            logger.info(f"生成信号: {signal.symbol} 权重 {signal.weight}")
            
        return signals
```

### 性能监控

```python
import time

class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}
        
    def record(self, name, duration):
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append(duration)
        
    def report(self):
        for name, durations in self.metrics.items():
            avg = sum(durations) / len(durations)
            print(f"{name}: 平均 {avg*1000:.2f}ms")

monitor = PerformanceMonitor()

# 在策略中使用
class MyStrategy(Strategy):
    def on_bar(self, context):
        start = time.time()
        
        signals = self._generate_signals(context)
        
        duration = time.time() - start
        monitor.record("signal_generation", duration)
        
        return signals
```

## 最佳实践

### 1. 分阶段部署

```bash
# 阶段1：模拟盘验证（1-2周）
python live_trading.py --mode=paper

# 阶段2：小资金实盘（1-2周）
python live_trading.py --capital=10000

# 阶段3：逐步加仓
python live_trading.py --capital=50000
python live_trading.py --capital=100000
```

### 2. 健康检查

```python
class HealthCheck:
    def check_data_source(self):
        """检查数据源连接"""
        pass
        
    def check_broker_connection(self):
        """检查券商连接"""
        pass
        
    def check_order_queue(self):
        """检查订单队列"""
        pass
        
    def run_all(self):
        checks = [
            ("数据源", self.check_data_source),
            ("券商连接", self.check_broker_connection),
            ("订单队列", self.check_order_queue),
        ]
        
        for name, check in checks:
            try:
                check()
                logger.info(f"✓ {name} 正常")
            except Exception as e:
                logger.error(f"✗ {name} 异常: {e}")
                alert_mgr.error(f"{name}检查失败", str(e))
```

### 3. 异常处理

```python
class RobustLiveEngine:
    def run(self):
        while True:
            try:
                self._run_one_bar()
            except DataSourceError as e:
                logger.error(f"数据源错误: {e}")
                alert_mgr.error("数据源异常", str(e))
                time.sleep(60)  # 等待1分钟后重试
            except BrokerError as e:
                logger.error(f"券商接口错误: {e}")
                alert_mgr.critical("券商接口异常", str(e))
                break  # 严重错误，停止交易
            except Exception as e:
                logger.exception("未知错误")
                alert_mgr.critical("系统异常", str(e))
                break
```

### 4. 定期对账

```python
def reconcile():
    """对账：比对系统持仓与券商实际持仓"""
    system_positions = get_system_positions()
    broker_positions = broker.get_all_positions()
    
    mismatches = []
    for symbol in set(system_positions.keys()) | set(broker_positions.keys()):
        sys_shares = system_positions.get(symbol, 0)
        broker_shares = broker_positions.get(symbol, 0)
        
        if sys_shares != broker_shares:
            mismatches.append({
                "symbol": symbol,
                "system": sys_shares,
                "broker": broker_shares,
                "diff": sys_shares - broker_shares
            })
            
    if mismatches:
        alert_mgr.warning("持仓不一致", str(mismatches))
        
    return mismatches

# 每日收盘后对账
schedule.every().day.at("15:30").do(reconcile)
```

## 故障排除

### 订单提交失败

```python
# 常见原因：
# 1. 资金不足
# 2. 涨跌停限制
# 3. 停牌
# 4. API 限流

# 解决方案：
try:
    order = order_mgr.submit_order(...)
except InsufficientFundsError:
    logger.warning("资金不足，跳过此订单")
except MarketHaltedError:
    logger.info("股票停牌，跳过")
except RateLimitError:
    logger.warning("API 限流，等待后重试")
    time.sleep(1)
    order = order_mgr.submit_order(...)
```

### 数据延迟

```python
# 检查数据时效性
def check_data_freshness(bar, max_delay=60):
    """检查数据是否新鲜（秒）"""
    now = datetime.now()
    data_time = datetime.combine(bar.date, datetime.min.time())
    delay = (now - data_time).total_seconds()
    
    if delay > max_delay:
        alert_mgr.warning(
            "数据延迟",
            f"数据延迟 {delay:.0f} 秒"
        )
        return False
    return True
```

## 相关文档

- [策略开发指南](./guide/01_basics.md)
- [CLI 工具指南](./cli.md)
- [工具模块指南](./tools.md)
