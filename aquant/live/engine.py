"""实盘交易引擎

提供将回测策略部署到实盘的完整框架。
"""

import time
from datetime import date, datetime, time as datetime_time
from typing import Any

import structlog

from aquant.broker.adapter import BrokerAdapter
from aquant.core.context import Context
from aquant.data.source import DataSource
from aquant.risk.guard import RiskGuard
from aquant.strategy.base import Strategy
from aquant.strategy.signal import Signal

logger = structlog.get_logger()


class LiveTradingEngine:
    """实盘交易引擎"""

    def __init__(
        self,
        strategy: Strategy,
        broker: BrokerAdapter,
        data_source: DataSource,
        risk_guards: list[RiskGuard] | None = None,
        trading_time: datetime_time = datetime_time(14, 30),  # 默认 14:30 交易
        max_daily_loss: float = 0.03,  # 日最大亏损 3%
        dry_run: bool = False,  # 是否为演练模式
    ):
        """
        Args:
            strategy: 交易策略
            broker: 券商适配器
            data_source: 数据源
            risk_guards: 风控规则列表
            trading_time: 每日交易时间
            max_daily_loss: 日最大亏损比例
            dry_run: 演练模式（不实际下单）
        """
        self.strategy = strategy
        self.broker = broker
        self.data_source = data_source
        self.risk_guards = risk_guards or []
        self.trading_time = trading_time
        self.max_daily_loss = max_daily_loss
        self.dry_run = dry_run

        self.daily_start_value = 0.0
        self.running = False

        logger.info(
            "实盘交易引擎初始化",
            dry_run=dry_run,
            trading_time=str(trading_time),
            max_daily_loss=f"{max_daily_loss * 100}%",
        )

    def start(self):
        """启动实盘交易引擎"""
        self.running = True
        logger.info("实盘交易引擎启动")

        try:
            while self.running:
                now = datetime.now()

                # 判断是否为交易时间
                if self._is_trading_time(now):
                    self._execute_trading()
                    # 等待到明天
                    time.sleep(86400 - now.hour * 3600 - now.minute * 60 - now.second)
                else:
                    # 每分钟检查一次
                    time.sleep(60)

        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error("实盘交易异常", error=str(e))
            raise
        finally:
            self.stop()

    def stop(self):
        """停止实盘交易引擎"""
        self.running = False
        logger.info("实盘交易引擎停止")

    def _is_trading_time(self, now: datetime) -> bool:
        """判断是否为交易时间"""
        # 检查是否为工作日
        if now.weekday() >= 5:  # 周六日
            return False

        # 检查时间
        current_time = now.time()
        target_hour = self.trading_time.hour
        target_minute = self.trading_time.minute

        return (
            current_time.hour == target_hour and current_time.minute == target_minute
        )

    def _execute_trading(self):
        """执行交易"""
        logger.info("开始执行交易", timestamp=datetime.now())

        try:
            # 记录日初资产
            if self.daily_start_value == 0:
                self.daily_start_value = self._get_total_value()

            # 检查日内亏损
            current_value = self._get_total_value()
            daily_loss = (
                (self.daily_start_value - current_value) / self.daily_start_value
            )

            if daily_loss > self.max_daily_loss:
                logger.warning(
                    "触发日最大亏损限制",
                    daily_loss=f"{daily_loss * 100:.2f}%",
                    max_daily_loss=f"{self.max_daily_loss * 100:.2f}%",
                )
                return

            # 构建上下文
            context = self._build_context()

            # 调用策略生成信号
            signals = self.strategy.on_bar(context)

            logger.info("策略生成信号", signal_count=len(signals))

            # 风控检查
            validated_signals = self._validate_signals(signals, context)

            logger.info("风控检查完成", validated_count=len(validated_signals))

            # 执行信号
            self._execute_signals(validated_signals, context)

            logger.info("交易执行完成")

        except Exception as e:
            logger.error("交易执行失败", error=str(e))
            self._send_alert(f"交易执行失败: {e}")

    def _build_context(self) -> Context:
        """构建策略上下文"""
        # TODO: 实现上下文构建逻辑
        # 需要从 broker 获取持仓信息，构建查询服务
        raise NotImplementedError("Context 构建逻辑需要根据实际需求实现")

    def _validate_signals(
        self, signals: list[Signal], context: Context
    ) -> list[Signal]:
        """风控检查信号"""
        validated = []

        for signal in signals:
            # 检查所有风控规则
            passed = True
            for guard in self.risk_guards:
                if not guard.check(signal, context):
                    logger.warning(
                        "信号被风控拒绝",
                        symbol=signal.symbol,
                        guard=guard.__class__.__name__,
                    )
                    passed = False
                    break

            if passed:
                validated.append(signal)

        return validated

    def _execute_signals(self, signals: list[Signal], context: Context):
        """执行信号"""
        total_value = self._get_total_value()

        # 计算目标持仓
        target_positions = {}
        for signal in signals:
            target_value = total_value * signal.weight
            # 获取当前价格
            bars = self.data_source.load_bars(date.today(), {signal.symbol})
            if signal.symbol in bars:
                target_shares = int(target_value / bars[signal.symbol].close)
                # A 股最小交易单位是 100 股
                target_shares = (target_shares // 100) * 100
                target_positions[signal.symbol] = target_shares

        # 执行调仓
        for symbol, target_shares in target_positions.items():
            current_shares = self.broker.get_position(symbol)
            delta = target_shares - current_shares

            if delta > 0:
                # 买入
                if self.dry_run:
                    logger.info(
                        "[演练模式] 买入订单",
                        symbol=symbol,
                        shares=delta,
                    )
                else:
                    order_id = self.broker.buy(symbol=symbol, shares=delta)
                    logger.info("买入订单已提交", symbol=symbol, shares=delta, order_id=order_id)

            elif delta < 0:
                # 卖出
                if self.dry_run:
                    logger.info(
                        "[演练模式] 卖出订单",
                        symbol=symbol,
                        shares=-delta,
                    )
                else:
                    order_id = self.broker.sell(symbol=symbol, shares=-delta)
                    logger.info("卖出订单已提交", symbol=symbol, shares=-delta, order_id=order_id)

    def _get_total_value(self) -> float:
        """计算总资产"""
        total = self.broker.get_cash()

        # TODO: 需要知道所有持仓的股票代码
        # 这里需要从 strategy 或其他地方获取股票池
        symbols = self._get_all_symbols()

        for symbol in symbols:
            position = self.broker.get_position(symbol)
            if position > 0:
                bars = self.data_source.load_bars(date.today(), {symbol})
                if symbol in bars:
                    total += position * bars[symbol].close

        return total

    def _get_all_symbols(self) -> list[str]:
        """获取所有需要关注的股票代码"""
        # TODO: 从策略中获取股票池
        # 这是一个简化的实现
        return []

    def _send_alert(self, message: str):
        """发送告警"""
        logger.warning("告警", message=message)
        # TODO: 实现实际的告警机制（邮件、短信、钉钉等）
