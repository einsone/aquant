# 策略基类

策略基类定义了策略的生命周期和接口。

## Strategy

::: aquant.strategy.base.Strategy
    options:
      show_root_heading: true
      show_source: true
      members:
        - on_start
        - on_bar
        - on_end
        - setup_subscriptions

## Signal

::: aquant.strategy.signal.Signal
    options:
      show_root_heading: true
      show_source: true

## RebalanceMode

策略支持两种调仓模式：

- `replace`: 完全替换，未在信号中的持仓清仓
- `add`: 增量调仓，仅调整信号中的标的

## 策略示例

```python
from aquant import Strategy, Signal

class MyStrategy(Strategy):
    """自定义策略示例"""
    
    warmup_period = 20  # 预热期天数
    rebalance_mode = "replace"  # 调仓模式
    
    def on_start(self, context):
        """回测开始前调用"""
        self.ma_period = 20
        
    def on_bar(self, context):
        """每个交易日调用，返回信号列表"""
        signals = []
        
        # 策略逻辑
        # ...
        
        return signals
    
    def on_end(self, context):
        """回测结束后调用"""
        pass
```
