# 订单撮合

订单撮合模块负责根据信号生成订单并执行。

## Matcher

::: aquant.matching.matcher.Matcher
    options:
      show_root_heading: true
      show_source: false

## CostModel

::: aquant.matching.cost.CostModel
    options:
      show_root_heading: true
      show_source: true

## 交易规则

### StockRules

::: aquant.matching.rules.StockRules
    options:
      show_root_heading: true
      show_source: true

### FuturesRules

::: aquant.matching.rules.FuturesRules
    options:
      show_root_heading: true
      show_source: true

## 自定义交易规则示例

```python
from aquant.matching.cost import CostModel

class MyTradingRules(CostModel):
    """自定义交易规则"""
    
    def calculate_cost(self, side: str, shares: int, price: float) -> tuple[float, float]:
        """计算交易成本
        
        Returns:
            (commission, stamp_duty)
        """
        commission = max(5.0, shares * price * 0.0003)
        stamp_duty = shares * price * 0.001 if side == "SELL" else 0.0
        return commission, stamp_duty
    
    def can_trade(self, symbol: str, side: str, current_position: int) -> bool:
        """是否可以交易"""
        if side == "SELL" and current_position <= 0:
            return False
        return True
    
    def round_shares(self, shares: float) -> int:
        """数量取整"""
        return int(shares // 100) * 100  # 100 股为一手
```
