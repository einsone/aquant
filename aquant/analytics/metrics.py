from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast


if TYPE_CHECKING:
    import polars as pl

    from aquant.portfolio.position import NavRecord


def total_return(nav: pl.Series) -> float:
    if len(nav) < 2:
        return 0.0
    return float(nav[-1] / nav[0] - 1)


def annualized_return(nav: pl.Series, trading_days: int = 252) -> float:
    if len(nav) < 2:
        return 0.0
    n = len(nav) - 1
    # 样本过短时指数年化会异常放大（如单日 1% → 1230%），降级为持有收益率
    if n < 5:
        return float(nav[-1] / nav[0] - 1)
    return float((nav[-1] / nav[0]) ** (trading_days / n) - 1)


def annualized_volatility(returns: pl.Series, trading_days: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    return float(cast("float", returns.std()) * math.sqrt(trading_days))


def sharpe(returns: pl.Series, risk_free: float = 0.0, trading_days: int = 252) -> float:
    vol = annualized_volatility(returns, trading_days)
    if vol == 0:
        return 0.0
    # 分子用几何年化，与 annualized_return 保持一致。
    # 分母 annualized_volatility 用 std * sqrt(252)（方差叠加），两者理论框架略有差异，
    # 但在日收益率较小时偏差可忽略，且与业界惯用的 Sharpe 计算方式一致。
    ann_ret = float((1 + cast("float", returns.mean())) ** trading_days - 1) - risk_free
    return ann_ret / vol


def max_drawdown(nav: pl.Series) -> tuple[float, int]:
    """返回 (最大回撤比例, 持续时间（交易日数）)。

    持续时间定义为：从最大回撤对应峰值到净值重新回到该峰值水平的天数。
    若回测结束时仍未恢复，则持续时间为峰值到序列末尾的天数。
    """
    if len(nav) < 2:
        return 0.0, 0

    peak = nav[0]
    max_dd = 0.0
    peak_idx = 0
    max_dd_peak_idx = 0  # 最大回撤对应的峰值位置

    for i, val in enumerate(nav):
        if val > peak:
            peak = val
            peak_idx = i
        dd = float((peak - val) / peak)
        if dd > max_dd:
            max_dd = dd
            max_dd_peak_idx = peak_idx

    if max_dd == 0.0:
        return 0.0, 0

    # 从最大回撤的峰值向后找净值首次恢复到该峰值水平的位置
    peak_val = float(nav[max_dd_peak_idx])
    recovery_idx = len(nav) - 1  # 默认：回测结束仍未恢复
    for j in range(max_dd_peak_idx + 1, len(nav)):
        if float(nav[j]) >= peak_val:
            recovery_idx = j
            break

    return max_dd, recovery_idx - max_dd_peak_idx


def calmar(nav: pl.Series, trading_days: int = 252) -> float:
    dd, _ = max_drawdown(nav)
    if dd == 0:
        return 0.0
    ann_ret = annualized_return(nav, trading_days)
    return ann_ret / dd


def information_ratio(returns: pl.Series, benchmark: pl.Series, trading_days: int = 252) -> float:
    """信息比率。两个 Series 须已按日期对齐，长度相同。"""
    excess = returns - benchmark
    std = cast("float", excess.std())
    if std == 0:
        return 0.0
    return cast("float", excess.mean()) / std * (trading_days**0.5)


def alpha_beta(returns: pl.Series, benchmark: pl.Series, trading_days: int = 252) -> tuple[float, float]:
    """返回 (年化 Alpha, Beta)。两个 Series 须已对齐。"""
    import polars as pl

    cov_matrix = pl.DataFrame({"r": returns, "b": benchmark}).select(pl.cov("r", "b").alias("cov"), pl.var("b").alias("var_b"))
    var_b = float(cov_matrix["var_b"][0])
    if var_b == 0:
        return 0.0, 0.0
    beta = float(cov_matrix["cov"][0]) / var_b
    alpha_daily = cast("float", returns.mean()) - beta * cast("float", benchmark.mean())
    alpha_ann = (1 + alpha_daily) ** trading_days - 1
    return alpha_ann, beta


def avg_position_count(daily_nav: list[NavRecord]) -> float:
    """每日平均持仓数量。从 daily_nav 的 position_count 字段读取。"""
    if not daily_nav:
        return 0.0
    return sum(n.position_count for n in daily_nav) / len(daily_nav)


def turnover(trade_log: list, daily_nav: list[NavRecord], trading_days: int = 252) -> float:
    """年化单边换手率。"""
    if not daily_nav or not trade_log:
        return 0.0
    total_traded = sum(t.shares * t.price for t in trade_log if t.side == "buy")
    avg_nav = sum(n.total for n in daily_nav) / len(daily_nav)
    if avg_nav == 0:
        return 0.0
    years = len(daily_nav) / trading_days
    return total_traded / avg_nav / years


def win_rate(trade_log: list) -> float:
    sells = [t for t in trade_log if t.side == "sell"]
    if not sells:
        return 0.0
    wins = sum(1 for t in sells if t.pnl > 0)
    return wins / len(sells)


def profit_loss_ratio(trade_log: list) -> float:
    sells = [t for t in trade_log if t.side == "sell"]
    wins = [t.pnl for t in sells if t.pnl > 0]
    losses = [abs(t.pnl) for t in sells if t.pnl < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    if avg_loss > 0:
        return avg_win / avg_loss
    return float("inf") if avg_win > 0 else 0.0


def compute_all(daily_nav: list[NavRecord], trade_log: list, benchmark_df: pl.DataFrame | None = None, trading_days: int = 252) -> dict:
    import polars as pl

    if not daily_nav:
        return {}

    nav_series = pl.Series([n.total for n in daily_nav])
    returns = nav_series.pct_change().drop_nulls()

    n_days = len(daily_nav)
    if n_days < trading_days:
        from aquant.log import get_logger as _get_logger

        _get_logger(__name__).warning("回测时长不足一年，年化收益率由几何放大计算，结果仅供参考", backtest_days=n_days, required_days=trading_days)

    dd, dd_duration = max_drawdown(nav_series)
    avg_pos = avg_position_count(daily_nav)
    metrics: dict = {
        "total_return": total_return(nav_series),
        "annualized_return": annualized_return(nav_series, trading_days),
        "annualized_volatility": annualized_volatility(returns, trading_days),
        "sharpe": sharpe(returns, trading_days=trading_days),
        "max_drawdown": dd,
        "max_drawdown_duration_days": dd_duration,
        "calmar": calmar(nav_series, trading_days),
        "avg_position_count": avg_pos,
        "win_rate": win_rate(trade_log),
        "profit_loss_ratio": profit_loss_ratio(trade_log),
        "turnover": turnover(trade_log, daily_nav, trading_days),
    }

    if benchmark_df is not None:
        required = {"date", "return"}
        missing = required - set(benchmark_df.columns)
        if missing:
            raise ValueError(f"benchmark_df 缺少必要列：{missing}，须包含 'date' 和 'return' 两列")

        nav_df = pl.DataFrame({"date": [n.date for n in daily_nav], "total": [n.total for n in daily_nav]})
        nav_returns = nav_df.with_columns(pl.col("total").pct_change().alias("return")).drop_nulls()

        joined = nav_returns.join(benchmark_df, on="date", how="inner")
        if len(joined) > 1:
            port_ret = joined["return"]
            bench_ret = joined["return_right"]

            # 基准覆盖率检查：inner join 丢弃不重叠日期，覆盖率过低时相对指标失真
            coverage = len(joined) / len(nav_returns)
            if coverage < 0.9:
                import logging as _logging

                _logging.getLogger(__name__).warning("基准日期覆盖率不足 90%%（%.1f%%），ir/alpha/beta/excess_return 存在样本偏差", coverage * 100)

            alpha, beta = alpha_beta(port_ret, bench_ret, trading_days)
            ir = information_ratio(port_ret, bench_ret, trading_days)
            # 前置 1.0 作为基准起点，确保第一日收益被纳入年化计算
            base = pl.Series([1.0])
            bench_nav = pl.concat([base, (1 + bench_ret).cum_prod()])
            port_nav_joined = pl.concat([base, (1 + port_ret).cum_prod()])
            bench_ann_ret = annualized_return(bench_nav, trading_days)
            # excess 使用相同日期范围的组合收益，避免时间窗口不匹配
            port_ann_ret_joined = annualized_return(port_nav_joined, trading_days)
            # sharpe_on_benchmark_dates：与 ir/alpha/beta 使用相同时间窗口，便于横向对比
            # 全量 sharpe 仍保留在 metrics["sharpe"] 中
            sharpe_joined = sharpe(port_ret, trading_days=trading_days)
            metrics.update({"alpha": alpha, "beta": beta, "information_ratio": ir, "benchmark_annualized_return": bench_ann_ret, "excess_annualized_return": port_ann_ret_joined - bench_ann_ret, "sharpe_on_benchmark_dates": sharpe_joined, "benchmark_coverage": round(coverage, 4)})

    return metrics
