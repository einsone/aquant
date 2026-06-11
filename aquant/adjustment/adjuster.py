from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from aquant.adjustment.corporate import BonusShares, CashDividend, RightsIssue
from aquant.log import get_logger


if TYPE_CHECKING:
    from datetime import date

    from aquant.adjustment.corporate import CorporateAction
    from aquant.data.source import DataSource
    from aquant.events.event import AdjustmentEvent, DelistEvent
    from aquant.market.bar import DayBar
    from aquant.matching.cost import CostModel
    from aquant.portfolio.portfolio import Portfolio

logger = get_logger(__name__)


class Adjuster:
    """企业行动与退市处理器。

    负责两件事：
    1. 除权除息：在派息日/除权日自动调整持仓的现金和股数。
    2. 退市强制平仓：在退市日将相关持仓以当日开盘价强制卖出。

    所有数据在引擎初始化时通过 preload 一次性加载，运行时按日期查表，
    不再访问数据库。
    """

    def __init__(self) -> None:
        # key = 触发日期，value = 当日需处理的企业行动列表
        # CashDividend 按 pay_date 索引，BonusShares / RightsIssue 按 ex_date 索引
        self._pending: dict[date, list[CorporateAction]] = defaultdict(list)
        # key = 退市日，value = 当日退市的标的代码列表
        self._delisted: dict[date, list[str]] = defaultdict(list)

    def preload(self, start: date, end: date, data_source: DataSource) -> None:
        """引擎初始化时调用一次，加载全回测区间的企业行动和退市数据。

        每种企业行动按各自的触发日期索引：
        - CashDividend  → pay_date
        - BonusShares   → ex_date
        - RightsIssue   → ex_date

        查询范围：触发日期 >= start，确保回测区间内所有需处理的企业行动
        都被加载，即使其 register_date（股权登记日）早于 start。
        """
        for action in data_source.load_adjustments(start, end):
            trigger_date = action.pay_date if isinstance(action, CashDividend) else action.ex_date
            self._pending[trigger_date].append(action)

        for dt, symbols in data_source.load_delisted(start, end).items():
            self._delisted[dt].extend(symbols)

    def has_actions_for_date(self, dt: date) -> bool:
        """判断指定日期是否有企业行动，供引擎决定是否插入 AdjustmentEvent。"""
        return bool(self._pending.get(dt))

    def delisted_symbols_for_date(self, dt: date) -> list[str]:
        """返回指定日期退市的标的代码列表，供引擎填充 DelistEvent.symbols。"""
        return self._delisted.get(dt, [])

    def apply(self, event: AdjustmentEvent, portfolio: Portfolio) -> None:
        """处理当日所有企业行动，调整持仓的现金和股数。

        在引擎的 ADJUSTMENT 阶段调用，早于策略的 SIGNAL 阶段，
        确保策略 on_bar 看到的持仓已是调整后的状态。
        """
        for action in self._pending.get(event.date, []):
            pos = portfolio.positions.get(action.symbol)
            if pos is None:
                continue

            if isinstance(action, CashDividend):
                # 将税后红利打入现金，并降低持仓成本。
                # 降低 cost_basis 的原因：分红本质上是拿回了部分投资成本，
                # 如果不调整，后续卖出时盈亏会被高估。
                cash = pos.shares * action.amount_per_share
                portfolio.cash += cash
                pos.cost_basis -= action.amount_per_share

            elif isinstance(action, BonusShares):
                # 按 ratio 比例增加股数。
                # 例：持有 1000 股，ratio=0.3，则增加 300 股，总计 1300 股。
                # cost_basis 摊薄（总成本不变，股数增加，单股成本降低）。
                # 新增份额的 tradeable_shares 不增加——送股当日不可卖出（T+1）。
                # 送股股数四舍五入（避免浮点截断，如 3 x 0.3 = 0.899... 被截为 0）
                new_shares = round(pos.shares * action.ratio)
                if new_shares == 0:
                    continue
                old_total_cost = pos.cost_basis * pos.shares
                pos.shares += new_shares
                pos.cost_basis = old_total_cost / pos.shares
                # 股数增加后同步更新市值，确保 base_value 当日准确
                pos.market_value = pos.shares * pos.last_close

            elif isinstance(action, RightsIssue):
                # 配股需要持股人主动出资认购，框架不自动处理。
                # 策略可通过查询数据源感知配股事件并自行决定是否认购。
                logger.debug("配股事件跳过，框架不自动处理认购", action=action)

    def force_close(self, event: DelistEvent, portfolio: Portfolio, bars: dict[str, DayBar], cost_model: CostModel) -> None:
        """退市强制平仓，在引擎的 DELIST 阶段调用。

        对 event.symbols 中当前仍有持仓的标的，以当日开盘价全仓卖出。
        无行情数据（已从交易所摘牌）时回退到 position.last_close 估值。
        跳过 Guard 链，直接调用 portfolio.apply_fill 结算，正常收取交易成本。
        """
        to_close = [s for s in event.symbols if s in portfolio.positions]
        if not to_close:
            return

        for symbol in to_close:
            pos = portfolio.positions[symbol]
            bar = bars.get(symbol)
            # 优先用当日开盘价；停牌或无行情时用最后已知收盘价估值
            price = bar.open if (bar and not bar.is_halted and bar.open > 0) else pos.last_close
            shares = pos.shares

            # 价格为 0（标的价值归零）时直接核销持仓，不走结算，避免强收最低佣金
            if price <= 0:
                del portfolio.positions[symbol]
                continue

            # 退市强制平仓解除 T+1 锁定，确保 tradeable_shares 不会变负
            pos.tradeable_shares = shares
            value = shares * price
            commission, stamp_duty = cost_model.compute_sell(value)
            portfolio.apply_fill(symbol=symbol, side="sell", shares=shares, fill_price=price, commission=commission, stamp_duty=stamp_duty, locked=False, dt=event.date)
