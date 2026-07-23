"""告警通知器核心类"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol

import structlog


if TYPE_CHECKING:
    from typing import Any


logger = structlog.get_logger()


class AlertLevel(IntEnum):
    """告警级别"""

    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class Channel(Protocol):
    """通知渠道协议"""

    def send(self, message: str, level: AlertLevel) -> bool:
        """发送通知

        Args:
            message: 告警消息
            level: 告警级别

        Returns:
            是否发送成功
        """
        ...


class Notifier:
    """告警通知器

    支持多通道通知，可根据告警级别过滤。

    示例：
        notifier = Notifier(min_level=AlertLevel.WARNING)
        notifier.add_channel(EmailChannel(smtp_host="smtp.gmail.com", ...))
        notifier.add_channel(DingTalkChannel(webhook_url="https://..."))

        notifier.send("风控触发：持仓超过限制", level=AlertLevel.ERROR)
    """

    def __init__(self, min_level: AlertLevel = AlertLevel.INFO):
        self.min_level = min_level
        self.channels: list[Channel] = []

    def add_channel(self, channel: Channel) -> Notifier:
        """添加通知渠道"""
        self.channels.append(channel)
        return self

    def send(self, message: str, level: AlertLevel = AlertLevel.INFO, **context: Any) -> bool:
        """发送告警

        Args:
            message: 告警消息
            level: 告警级别
            **context: 附加上下文信息

        Returns:
            至少一个渠道发送成功返回 True
        """
        if level < self.min_level:
            logger.debug("告警级别低于阈值，跳过", message=message, level=level.name, min_level=self.min_level.name)
            return True

        # 构造完整消息
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{level.name}] {timestamp}\n{message}"

        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            full_message += f"\n\n上下文:\n{context_str}"

        # 发送到所有渠道
        success = False
        for channel in self.channels:
            try:
                if channel.send(full_message, level):
                    success = True
                    logger.info("告警发送成功", channel=type(channel).__name__, level=level.name)
            except Exception as e:
                logger.error("告警发送失败", channel=type(channel).__name__, error=str(e))

        if not success and self.channels:
            logger.warning("所有告警渠道发送失败", message=message)

        return success
