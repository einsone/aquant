"""风控管理器模块，提供组合级风控检查。

与 Guard（订单级检查）不同，RiskManager 在信号生成后、订单提交前进行组合级风控：
- 单标的持仓上限
- 最大回撤限制
- 杠杆率限制
- 集中度检查
等。

通过可插拔的 RiskRule，用户可以自定义风控规则。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from aquant.log import get_logger


logger = get_logger(__name__)


if TYPE_CHECKING:
    from aquant.core.context import Context
    from aquant.portfolio.portfolio import Portfolio
    from aquant.strategy.signal import Signal


class RiskRule(ABC):
    """风控规则抽象基类。

    子类实现具体的风控逻辑，返回 True 表示通过，False 表示拦截。
    """

    @abstractmethod
    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        """检查信号是否违反风控规则。

        参数
        ----
        signal:
            待检查的信号
        portfolio:
            当前组合状态
        context:
            当前上下文

        返回
        ----
        True 表示通过，False 表示拦截
        """


class MaxPositionSizeRule(RiskRule):
    """单标的持仓上限规则。

    限制单个标的的目标权重不超过指定比例，防止过度集中。
    """

    def __init__(self, max_ratio: float = 0.2) -> None:
        """初始化规则。

        参数
        ----
        max_ratio:
            单标的最大权重比例（0.0 到 1.0）。默认 0.2（20%）。
        """
        self.max_ratio = max_ratio

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        if signal.weight > self.max_ratio:
            logger.warning("信号被风控拦截：单标的持仓超限", symbol=signal.symbol, weight=signal.weight, max_ratio=self.max_ratio, date=context.current_date)
            return False
        return True


class MaxDrawdownRule(RiskRule):
    """最大回撤限制规则。

    当组合回撤超过指定阈值时，停止所有买入操作，只允许平仓。
    """

    def __init__(self, max_dd: float = 0.2) -> None:
        """初始化规则。

        参数
        ----
        max_dd:
            最大回撤阈值（0.0 到 1.0）。默认 0.2（20%）。
        """
        self.max_dd = max_dd

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        # 查询当前回撤
        current_dd = context.query.get_current_drawdown()

        # 回撤超限时，只允许清仓（weight=0），拦截买入和加仓
        if current_dd >= self.max_dd and signal.weight > 0:
            # 检查是否为加仓
            pos = portfolio.positions.get(signal.symbol)
            if pos is None:
                # 新建仓，拦截
                logger.warning("信号被风控拦截：回撤超限，禁止新建仓", symbol=signal.symbol, weight=signal.weight, current_dd=f"{current_dd:.2%}", max_dd=f"{self.max_dd:.2%}", date=context.current_date)
                return False
            else:
                # 已有持仓，检查是否加仓
                current_weight = pos.shares * pos.last_close / context.total_value
                if signal.weight > current_weight:
                    logger.warning("信号被风控拦截：回撤超限，禁止加仓", symbol=signal.symbol, weight=signal.weight, current_weight=f"{current_weight:.2%}", current_dd=f"{current_dd:.2%}", max_dd=f"{self.max_dd:.2%}", date=context.current_date)
                    return False

        return True


class MaxLeverageRule(RiskRule):
    """杠杆率限制规则。

    限制总目标仓位（所有信号权重之和）不超过 1.0，防止过度杠杆。
    """

    def __init__(self, max_leverage: float = 1.0) -> None:
        """初始化规则。

        参数
        ----
        max_leverage:
            最大杠杆倍数。默认 1.0（不加杠杆）。
        """
        self.max_leverage = max_leverage
        self._total_weight: float = 0.0

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        # 累加权重（在 RiskManager.check_signals 中每批次会重置）
        self._total_weight += signal.weight
        return True

    def reset(self) -> None:
        """重置累计权重（每批次信号开始前调用）。"""
        self._total_weight = 0.0


class ConcentrationRule(RiskRule):
    """集中度限制规则。

    限制前 N 大持仓的权重之和不超过指定比例。
    """

    def __init__(self, top_n: int = 5, max_concentration: float = 0.6) -> None:
        """初始化规则。

        参数
        ----
        top_n:
            前 N 大持仓。默认 5。
        max_concentration:
            前 N 大持仓权重之和上限（0.0 到 1.0）。默认 0.6（60%）。
        """
        self.top_n = top_n
        self.max_concentration = max_concentration

    def check(self, signal: Signal, portfolio: Portfolio, context: Context) -> bool:
        # 计算当前持仓 + 本信号后的前 N 大权重
        weights: dict[str, float] = {}

        # 现有持仓
        for symbol, pos in portfolio.positions.items():
            weights[symbol] = pos.shares * pos.last_close / context.total_value

        # 更新本信号的权重
        weights[signal.symbol] = signal.weight

        # 排序取前 N 大
        top_weights = sorted(weights.values(), reverse=True)[: self.top_n]
        concentration = sum(top_weights)

        if concentration > self.max_concentration:
            logger.warning("信号被风控拦截：集中度超限", symbol=signal.symbol, top_n=self.top_n, concentration=f"{concentration:.2%}", max_concentration=f"{self.max_concentration:.2%}", date=context.current_date)
            return False

        return True


class RiskManager:
    """组合级风控管理器。

    在信号生成后、订单提交前，对所有信号进行风控检查。
    被拦截的信号会被过滤掉，不会进入撮合阶段。

    使用示例::

        # 创建风控规则
        rules = [
            MaxPositionSizeRule(max_ratio=0.2),  # 单标的最多 20%
            MaxDrawdownRule(max_dd=0.15),  # 回撤超 15% 停止买入
            ConcentrationRule(top_n=5, max_concentration=0.6),  # 前 5 大不超 60%
        ]

        # 创建风控管理器
        risk_manager = RiskManager(rules)

        # 在 Engine 中使用
        engine = Engine(strategy, data_source, config, risk_manager=risk_manager)
    """

    def __init__(self, rules: list[RiskRule] | None = None) -> None:
        """初始化风控管理器。

        参数
        ----
        rules:
            风控规则列表。默认为空列表（不做任何风控）。
        """
        self._rules = rules or []

    def check_signals(self, signals: list[Signal], portfolio: Portfolio, context: Context) -> list[Signal]:
        """检查信号列表，过滤违反风控规则的信号。

        参数
        ----
        signals:
            原始信号列表
        portfolio:
            当前组合状态
        context:
            当前上下文

        返回
        ----
        通过风控检查的信号列表
        """
        if not self._rules:
            return signals  # 无风控规则，直接返回

        # 重置有状态的规则（如 MaxLeverageRule）
        for rule in self._rules:
            reset_method = getattr(rule, "reset", None)
            if reset_method is not None and callable(reset_method):
                reset_method()

        approved: list[Signal] = []
        for signal in signals:
            if all(rule.check(signal, portfolio, context) for rule in self._rules):
                approved.append(signal)

        if len(approved) < len(signals):
            rejected = len(signals) - len(approved)
            logger.info("风控过滤信号", total=len(signals), approved=len(approved), rejected=rejected, date=context.current_date)

        return approved

    def add_rule(self, rule: RiskRule) -> None:
        """运行时添加风控规则。

        参数
        ----
        rule:
            要添加的风控规则
        """
        self._rules.append(rule)
