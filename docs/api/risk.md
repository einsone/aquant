# 风控管理

可插拔的风控规则系统。

## RiskManager

::: aquant.risk.RiskManager
    options:
      show_root_heading: true
      show_source: true
      members:
        - check_signals
        - add_rule
        - clear_rules

## RiskRule

::: aquant.risk.RiskRule
    options:
      show_root_heading: true
      show_source: true

## 内置风控规则

### MaxPositionSizeRule

::: aquant.risk.MaxPositionSizeRule
    options:
      show_root_heading: true
      show_source: true

### MaxDrawdownRule

::: aquant.risk.MaxDrawdownRule
    options:
      show_root_heading: true
      show_source: true

### MaxLeverageRule

::: aquant.risk.MaxLeverageRule
    options:
      show_root_heading: true
      show_source: true

### ConcentrationRule

::: aquant.risk.ConcentrationRule
    options:
      show_root_heading: true
      show_source: true

## 自定义风控规则示例

```python
from aquant.risk import RiskRule

class MyRiskRule(RiskRule):
    """自定义风控规则"""
    
    def __init__(self, threshold: float):
        self.threshold = threshold
    
    def check(self, signal, portfolio, context) -> bool:
        """检查信号是否通过风控"""
        # 自定义检查逻辑
        if some_condition:
            return False  # 拦截
        return True  # 通过

# 使用自定义规则
risk_manager = RiskManager(rules=[
    MyRiskRule(threshold=0.1),
])
```
