"""具体的通知渠道实现"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import httpx
import structlog


if TYPE_CHECKING:
    from aquant.alert.notifier import AlertLevel


logger = structlog.get_logger()


class EmailChannel:
    """邮件通知渠道

    使用 SMTP 发送邮件通知。

    示例：
        channel = EmailChannel(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            username="your@gmail.com",
            password="your_app_password",
            from_addr="your@gmail.com",
            to_addrs=["alert@company.com"]
        )
    """

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str, from_addr: str, to_addrs: list[str], use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    def send(self, message: str, level: AlertLevel) -> bool:
        """发送邮件通知"""
        try:
            # 构造邮件
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = f"[Aquant Alert] {level.name}"
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)

            # 发送邮件
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            return True

        except Exception as e:
            logger.error("邮件发送失败", error=str(e))
            return False


class DingTalkChannel:
    """钉钉机器人通知渠道

    使用钉钉自定义机器人发送通知。

    示例：
        channel = DingTalkChannel(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            secret="SEC..."  # 可选，加签密钥
        )
    """

    def __init__(self, webhook_url: str, secret: str | None = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def send(self, message: str, level: AlertLevel) -> bool:
        """发送钉钉通知"""
        try:
            # 构造请求
            data = {"msgtype": "text", "text": {"content": message}}

            # 如果配置了加签，计算签名
            headers = {"Content-Type": "application/json"}
            url = self.webhook_url

            if self.secret:
                import base64
                import hashlib
                import hmac
                import time
                from urllib.parse import quote_plus

                timestamp = str(round(time.time() * 1000))
                secret_enc = self.secret.encode("utf-8")
                string_to_sign = f"{timestamp}\n{self.secret}"
                string_to_sign_enc = string_to_sign.encode("utf-8")
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = quote_plus(base64.b64encode(hmac_code))
                url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

            # 发送请求
            response = httpx.post(url, json=data, headers=headers, timeout=10.0)
            response.raise_for_status()

            result = response.json()
            if result.get("errcode") == 0:
                return True

            logger.error("钉钉通知失败", errcode=result.get("errcode"), errmsg=result.get("errmsg"))
            return False

        except Exception as e:
            logger.error("钉钉通知发送失败", error=str(e))
            return False


class WeComChannel:
    """企业微信机器人通知渠道

    使用企业微信群机器人发送通知。

    示例：
        channel = WeComChannel(
            webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        )
    """

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str, level: AlertLevel) -> bool:
        """发送企业微信通知"""
        try:
            # 构造请求
            data = {"msgtype": "text", "text": {"content": message}}

            # 发送请求
            response = httpx.post(self.webhook_url, json=data, timeout=10.0)
            response.raise_for_status()

            result = response.json()
            if result.get("errcode") == 0:
                return True

            logger.error("企业微信通知失败", errcode=result.get("errcode"), errmsg=result.get("errmsg"))
            return False

        except Exception as e:
            logger.error("企业微信通知发送失败", error=str(e))
            return False
