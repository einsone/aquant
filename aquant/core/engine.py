from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from aquant.adjustment.adjuster import Adjuster
from aquant.core.context import Context
from aquant.data.source import DataSource
from aquant.events.event import AdjustmentEvent, DayStartEvent, DelistEvent, FillEvent, Phase, SignalEvent, ValuationEvent
from aquant.events.queue import EventQueue
from aquant.matching.cost import CostModel
from aquant.matching.matcher import Matcher
from aquant.portfolio.portfolio import Portfolio
from aquant.strategy.signal import Signal


if TYPE_CHECKING:
    from aquant.market.bar import DayBar
    from aquant.strategy.base import Strategy


class BacktestConfig(BaseModel):
    start: date = Field(description="回测起始日期。框架取 load_calendar 返回列表中 >= start 的第一个交易日作为实际起始，无需精确到交易日。")
    end: date = Field(description="回测结束日期（含）。框架取 load_calendar 返回列表中 <= end 的最后一个交易日作为实际结束，无需精确到交易日。")
    initial_capital: float = Field(gt=0, description="初始资金（元）。")
    commission_rate: float = Field(default=0.0003, ge=0, description="佣金费率，按成交金额双边收取。默认万分之三（0.0003）。")
    min_commission: float = Field(default=5.0, ge=0, description="单笔最低佣金（元）。默认 5 元。")
    stamp_duty_rate: float = Field(default=0.001, ge=0, description="印花税税率，仅卖出单边收取。默认千分之一（0.001）。税率历史上有调整（2008 年降至 0.1%，2023 年再降至 0.05%），长周期回测可按实际修改。")
    slippage_rate: float = Field(default=0.0005, ge=0, description="滑点比例，按成交金额估算市场冲击成本。默认万分之五（0.0005）。")
    cash_buffer: float = Field(default=0.02, ge=0, lt=1, description="现金缓冲比例，预留此比例的资金不参与投资，防止手数取整导致超额委托。默认 2%（0.02）。")
    rebalance_threshold: float = Field(default=0.0, ge=0, description="调仓阈值。目标权重与当前权重之差小于此值时不触发交易，避免微小信号变化产生无效换手。默认 0.0（每次都调仓）。")
    volume_cap_ratio: float = Field(default=1.0, gt=0, le=1, description="单笔委托量占当日总成交量的上限比例。默认 1.0（不限制）。设为较小值可模拟大资金的市场冲击约束。")
    benchmark: Any = Field(default=None, description="基准收益序列，类型为 pl.DataFrame，须含 date 和 return 两列。用于计算 Alpha、Beta、信息比率等相对指标。为 None 时跳过。")

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: date, info: Any) -> date:
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end 必须晚于或等于 start")
        return v

    model_config = {"arbitrary_types_allowed": True}


class BacktestResult:
    def __init__(self, portfolio: Portfolio, benchmark_df: object = None) -> None:
        self.portfolio = portfolio
        self.metrics: dict = {}
        self._benchmark_df = benchmark_df

    def compute_metrics(self, benchmark_df: object = None) -> BacktestResult:
        from aquant.analytics import metrics as m

        effective_benchmark = benchmark_df if benchmark_df is not None else self._benchmark_df
        self.metrics = m.compute_all(daily_nav=self.portfolio._daily_nav, trade_log=self.portfolio.trade_log, benchmark_df=effective_benchmark)
        return self

    def report(self, path: str | None = None) -> str:
        lines = ["# Backtest Report\n"]
        for k, v in self.metrics.items():
            if isinstance(v, float):
                lines.append(f"- **{k}**: {v:.4f}")
            else:
                lines.append(f"- **{k}**: {v}")
        text = "\n".join(lines)
        if path:
            from pathlib import Path

            Path(path).write_text(text, encoding="utf-8")
        return text


class Engine:
    def __init__(self, strategy: Strategy, data_source: DataSource, config: BacktestConfig) -> None:
        self._strategy = strategy
        self._data_source = data_source
        self._config = config

        trading_days = sorted(d for d in data_source.load_calendar(config.start, config.end) if config.start <= d <= config.end)
        if not trading_days:
            raise ValueError(f"{config.start} 到 {config.end} 区间内没有交易日")

        self._adjuster = Adjuster()
        self._portfolio = Portfolio(config.initial_capital)
        self._cost_model = CostModel.from_config(config)
        self._matcher = Matcher(cost_model=self._cost_model, cash_buffer=config.cash_buffer, rebalance_threshold=config.rebalance_threshold, volume_cap_ratio=config.volume_cap_ratio)

        self._adjuster.preload(config.start, config.end, data_source)
        self._queue = self._build_queue(trading_days)

        self._day_bars: dict[str, DayBar] = {}
        self._day_is_warmup: bool = strategy.warmup_period > 0
        self._warmup_remaining: int = strategy.warmup_period
        self._pending_signals: list[Signal] = []  # T 日信号，等待 T+1 FILL 阶段执行

    def _build_queue(self, trading_days: list[date]) -> EventQueue:
        q = EventQueue()
        for dt in trading_days:
            q.push(DayStartEvent(date=dt))
            q.push(FillEvent(date=dt))  # 执行前一日缓存的信号（第一日无缓存，FILL 阶段为空操作）

            if self._adjuster.has_actions_for_date(dt):
                q.push(AdjustmentEvent(date=dt))

            delist_symbols = self._adjuster.delisted_symbols_for_date(dt)
            if delist_symbols:
                q.push(DelistEvent(date=dt, symbols=delist_symbols))

            q.push(SignalEvent(date=dt))
            q.push(ValuationEvent(date=dt))

        q.seal()
        return q

    def _build_context(self, dt: date) -> Context:
        return Context(current_date=dt, positions=self._portfolio.position_views(), cash=self._portfolio.cash, total_value=self._portfolio.total_value)

    def run(self) -> BacktestResult:
        start_context = self._build_context(self._config.start)
        self._strategy.on_start(start_context)

        for event in self._queue:
            if event.phase == Phase.DAY_START:
                self._portfolio.reset_tradeable()
                self._day_is_warmup = self._warmup_remaining > 0

            elif event.phase == Phase.FILL:
                # 执行前一交易日 SIGNAL 阶段缓存的信号，以今日（T+1）开盘价成交
                # replace 模式下即使信号为空（策略返回 []），也要进入 execute 以清仓现有持仓
                # 预热期内不执行撮合
                has_pending = bool(self._pending_signals)
                replace_needs_liquidation = not self._day_is_warmup and self._strategy.rebalance_mode == "replace" and bool(self._portfolio.symbols)
                if has_pending or replace_needs_liquidation:
                    symbols = {s.symbol for s in self._pending_signals} | self._portfolio.symbols
                    self._day_bars = self._data_source.load_bars(event.date, symbols)
                    base_value = self._portfolio.total_value
                    self._matcher.execute(self._pending_signals, self._portfolio, self._day_bars, base_value, event.date, self._strategy.rebalance_mode)
                    self._pending_signals = []

            elif event.phase == Phase.ADJUSTMENT:
                assert isinstance(event, AdjustmentEvent)
                self._adjuster.apply(event, self._portfolio)

            elif event.phase == Phase.DELIST:
                assert isinstance(event, DelistEvent)
                delist_bars = self._data_source.load_bars(event.date, set(event.symbols))
                self._adjuster.force_close(event, self._portfolio, delist_bars, self._cost_model)

            elif event.phase == Phase.SIGNAL:
                context = self._build_context(event.date)
                if self._day_is_warmup:
                    self._warmup_remaining -= 1
                    self._strategy.on_bar(context)
                else:
                    raw_signals = self._strategy.on_bar(context)
                    # 复制 Signal 对象再填入 signal_date，避免改变策略持有的引用
                    # meta 做浅拷贝，防止策略后续修改 meta dict 影响缓存的信号
                    self._pending_signals = [Signal(symbol=s.symbol, weight=s.weight, signal_date=event.date, meta=dict(s.meta)) for s in raw_signals]

            elif event.phase == Phase.VALUATION:
                if not self._day_is_warmup:
                    # FILL 阶段已加载 day_bars；若当日无待执行信号则补充加载持仓行情
                    if not self._day_bars and self._portfolio.symbols:
                        self._day_bars = self._data_source.load_bars(event.date, self._portfolio.symbols)
                    self._portfolio.take_snapshot(event.date, self._day_bars)
                self._day_bars = {}  # 无论是否预热，每日清空，防止 stale bars 泄漏到次日

        end_context = self._build_context(self._config.end)
        self._strategy.on_end(end_context)

        result = BacktestResult(portfolio=self._portfolio, benchmark_df=self._config.benchmark)
        result.compute_metrics()
        return result
