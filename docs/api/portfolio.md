# 组合管理

组合管理模块负责持仓、资金和净值管理。

## Portfolio

::: aquant.portfolio.portfolio.Portfolio
    options:
      show_root_heading: true
      show_source: false
      members:
        - total_value
        - cash
        - positions
        - symbols
        - trade_log

## Position

持仓信息数据类，包含：

- `symbol`: 标的代码
- `quantity`: 持仓数量
- `available_quantity`: 可交易数量（T+1 限制）
- `avg_cost`: 平均成本
- `market_value`: 市值
- `unrealized_pnl`: 浮动盈亏

## Trade

交易记录数据类，包含：

- `date`: 交易日期
- `symbol`: 标的代码
- `side`: 买卖方向（BUY/SELL）
- `quantity`: 数量
- `price`: 成交价
- `amount`: 成交金额
- `commission`: 佣金
- `stamp_duty`: 印花税

## 查询服务

::: aquant.portfolio.query.PortfolioQueryService
    options:
      show_root_heading: true
      show_source: false
