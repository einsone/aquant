"""告警系统

提供多种告警渠道：邮件、短信、钉钉、企业微信等。
"""

import json
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

import requests
import structlog


logger = structlog.get_logger()


class AlertLevel(StrEnum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(ABC):
    """告警渠道抽象基类"""

    @abstractmethod
    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送告警

        Args:
            level: 告警级别
            title: 告警标题
            message: 告警内容
            extra: 额外信息
        """
        pass


class ConsoleAlertChannel(AlertChannel):
    """控制台告警（仅用于开发测试）"""

    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        log_func = {AlertLevel.INFO: logger.info, AlertLevel.WARNING: logger.warning, AlertLevel.ERROR: logger.error, AlertLevel.CRITICAL: logger.critical}[level]

        log_func("告警", title=title, message=message, extra=extra)


class EmailAlertChannel(AlertChannel):
    """邮件告警"""

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str, from_addr: str, to_addrs: list[str]):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        import smtplib
        from email.mime.text import MIMEText

        # 构建邮件内容
        content = f"""
告警级别：{level.value.upper()}
告警标题：{title}

{message}
"""
        if extra:
            content += f"\n额外信息：\n{json.dumps(extra, indent=2, ensure_ascii=False)}"

        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = f"[{level.value.upper()}] {title}"
        msg["From"] = self.from_addr
        msg["To"] = ",".join(self.to_addrs)

        try:
            # 发送邮件
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info("邮件告警已发送", title=title, level=level.value)

        except Exception as e:
            logger.error("邮件告警发送失败", error=str(e))


class DingTalkAlertChannel(AlertChannel):
    """钉钉告警"""

    def __init__(self, webhook_url: str, secret: str | None = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        import hashlib
        import hmac
        import time
        from urllib.parse import quote_plus

        # 构建消息内容
        content = f"**{title}**\n\n{message}"
        if extra:
            content += f"\n\n```json\n{json.dumps(extra, indent=2, ensure_ascii=False)}\n```"

        # 添加告警级别标记
        level_emoji = {AlertLevel.INFO: "ℹ️", AlertLevel.WARNING: "⚠️", AlertLevel.ERROR: "❌", AlertLevel.CRITICAL: "🔥"}
        content = f"{level_emoji[level]} {content}"

        # 签名
        url = self.webhook_url
        if self.secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{self.secret}"
            hmac_code = hmac.new(self.secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
            sign = quote_plus(hmac_code.hex())
            url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

        # 发送消息
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": content}}

        try:
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()

            result = response.json()
            if result.get("errcode") == 0:
                logger.info("钉钉告警已发送", title=title, level=level.value)
            else:
                logger.error("钉钉告警发送失败", result=result)

        except Exception as e:
            logger.error("钉钉告警发送异常", error=str(e))


class WeChatWorkAlertChannel(AlertChannel):
    """企业微信告警"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        # 构建消息内容
        content = f"**{title}**\n{message}"
        if extra:
            content += f"\n\n```json\n{json.dumps(extra, indent=2, ensure_ascii=False)}\n```"

        # 添加告警级别标记
        level_text = {AlertLevel.INFO: "信息", AlertLevel.WARNING: "警告", AlertLevel.ERROR: "错误", AlertLevel.CRITICAL: "严重"}
        content = f"[{level_text[level]}] {content}"

        # 发送消息
        payload = {"msgtype": "markdown", "markdown": {"content": content}}

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()

            result = response.json()
            if result.get("errcode") == 0:
                logger.info("企业微信告警已发送", title=title, level=level.value)
            else:
                logger.error("企业微信告警发送失败", result=result)

        except Exception as e:
            logger.error("企业微信告警发送异常", error=str(e))


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.channels: list[AlertChannel] = []

    def add_channel(self, channel: AlertChannel):
        """添加告警渠道

        Args:
            channel: 告警渠道
        """
        self.channels.append(channel)

    def send(self, level: AlertLevel, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送告警到所有渠道

        Args:
            level: 告警级别
            title: 告警标题
            message: 告警内容
            extra: 额外信息
        """
        if not self.channels:
            logger.warning("未配置告警渠道，告警未发送", title=title)
            return

        for channel in self.channels:
            try:
                channel.send(level, title, message, extra)
            except Exception as e:
                logger.error("告警渠道发送失败", channel=type(channel).__name__, error=str(e))

    def info(self, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送信息级别告警"""
        self.send(AlertLevel.INFO, title, message, extra)

    def warning(self, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送警告级别告警"""
        self.send(AlertLevel.WARNING, title, message, extra)

    def error(self, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送错误级别告警"""
        self.send(AlertLevel.ERROR, title, message, extra)

    def critical(self, title: str, message: str, extra: dict[str, Any] | None = None):
        """发送严重级别告警"""
        self.send(AlertLevel.CRITICAL, title, message, extra)
