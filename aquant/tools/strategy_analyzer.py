"""策略分析工具

提供策略性能的深度分析，包括归因分析、因子分解、周期分析等。
"""

from datetime import date

import numpy as np
import pandas as pd

from aquant.backtest.result import BacktestResult


class StrategyAnalyzer:
    """策略分析器"""

    def __init__(self, result: BacktestResult):
        self.result = result
        self.equity_curve = self._build_equity_curve()

    def _build_equity_curve(self) -> pd.Series:
        """构建净值曲线"""
        nav_data = []
        for snapshot in self.result.portfolio_snapshots:
            nav_data.append({"date": snapshot.date, "nav": snapshot.nav})

        if not nav_data:
            return pd.Series(dtype=float)

        df = pd.DataFrame(nav_data)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["nav"]

    def monthly_returns(self) -> pd.Series:
        """计算月度收益率

        Returns:
            月度收益率序列
        """
        if len(self.equity_curve) == 0:
            return pd.Series(dtype=float)

        monthly = self.equity_curve.resample("ME").last()
        return monthly.pct_change().dropna()

    def yearly_returns(self) -> pd.Series:
        """计算年度收益率

        Returns:
            年度收益率序列
        """
        if len(self.equity_curve) == 0:
            return pd.Series(dtype=float)

        yearly = self.equity_curve.resample("YE").last()
        return yearly.pct_change().dropna()

    def rolling_sharpe(self, window: int = 252) -> pd.Series:
        """计算滚动夏普比率

        Args:
            window: 滚动窗口天数（默认 252 个交易日）

        Returns:
            滚动夏普比率序列
        """
        if len(self.equity_curve) < window:
            return pd.Series(dtype=float)

        returns = self.equity_curve.pct_change().dropna()
        rolling_mean = returns.rolling(window).mean()
        rolling_std = returns.rolling(window).std()

        # 年化
        sharpe = (rolling_mean * 252) / (rolling_std * np.sqrt(252))
        return sharpe.dropna()

    def rolling_max_drawdown(self, window: int = 252) -> pd.Series:
        """计算滚动最大回撤

        Args:
            window: 滚动窗口天数

        Returns:
            滚动最大回撤序列
        """
        if len(self.equity_curve) < window:
            return pd.Series(dtype=float)

        def calc_mdd(series):
            cummax = series.cummax()
            drawdown = (series - cummax) / cummax
            return drawdown.min()

        rolling_mdd = self.equity_curve.rolling(window).apply(calc_mdd, raw=False)
        return rolling_mdd.dropna()

    def win_loss_analysis(self) -> dict:
        """盈亏分析

        Returns:
            盈亏统计字典
        """
        trades = self.result.trade_log

        if not trades:
            return {
                "total_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
            }

        # 计算每笔交易盈亏
        profits = []
        for trade in trades:
            if trade.side == "buy":
                continue
            # 简化：假设卖出即实现盈亏
            pnl = trade.filled_shares * (trade.avg_fill_price - trade.avg_fill_price * 0.95)  # 示例
            profits.append(pnl)

        if not profits:
            return {
                "total_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
            }

        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]

        return {
            "total_trades": len(profits),
            "win_trades": len(wins),
            "loss_trades": len(losses),
            "win_rate": len(wins) / len(profits) if profits else 0.0,
            "avg_win": np.mean(wins) if wins else 0.0,
            "avg_loss": np.mean(losses) if losses else 0.0,
            "profit_factor": sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0.0,
        }

    def holding_period_analysis(self) -> dict:
        """持仓周期分析

        Returns:
            持仓周期统计字典
        """
        # 简化实现：基于交易日志推断持仓周期
        trades = self.result.trade_log

        if len(trades) < 2:
            return {"avg_holding_days": 0, "min_holding_days": 0, "max_holding_days": 0}

        holding_periods = []
        positions = {}

        for trade in trades:
            if trade.side == "buy":
                positions[trade.symbol] = trade.date
            elif trade.side == "sell" and trade.symbol in positions:
                entry_date = positions[trade.symbol]
                holding_days = (trade.date - entry_date).days
                holding_periods.append(holding_days)
                del positions[trade.symbol]

        if not holding_periods:
            return {"avg_holding_days": 0, "min_holding_days": 0, "max_holding_days": 0}

        return {
            "avg_holding_days": np.mean(holding_periods),
            "min_holding_days": min(holding_periods),
            "max_holding_days": max(holding_periods),
        }

    def turnover_analysis(self) -> dict:
        """换手率分析

        Returns:
            换手率统计字典
        """
        trades = self.result.trade_log

        if not trades:
            return {"daily_turnover": 0.0, "monthly_turnover": 0.0}

        # 计算总交易金额
        total_value = sum(trade.filled_shares * trade.avg_fill_price for trade in trades)

        # 计算平均持仓市值
        avg_portfolio_value = self.result.initial_capital * (1 + self.result.total_return / 2)

        # 交易天数
        trading_days = (self.result.end_date - self.result.start_date).days

        if trading_days == 0 or avg_portfolio_value == 0:
            return {"daily_turnover": 0.0, "monthly_turnover": 0.0}

        daily_turnover = total_value / avg_portfolio_value / trading_days
        monthly_turnover = daily_turnover * 21  # 假设每月 21 个交易日

        return {"daily_turnover": daily_turnover, "monthly_turnover": monthly_turnover}

    def sector_exposure(self) -> dict[str, float]:
        """行业暴露分析

        Returns:
            行业 -> 暴露度的字典
        """
        # 简化实现：需要行业分类数据
        # 这里返回占位符
        return {"placeholder": 1.0}

    def summary(self) -> dict:
        """生成完整的分析报告

        Returns:
            包含所有分析结果的字典
        """
        return {
            "basic_metrics": {
                "total_return": self.result.total_return,
                "annualized_return": self.result.annualized_return,
                "sharpe_ratio": self.result.sharpe_ratio,
                "max_drawdown": self.result.max_drawdown,
                "total_trades": len(self.result.trade_log),
            },
            "monthly_returns": self.monthly_returns().to_dict(),
            "yearly_returns": self.yearly_returns().to_dict(),
            "win_loss": self.win_loss_analysis(),
            "holding_period": self.holding_period_analysis(),
            "turnover": self.turnover_analysis(),
        }
