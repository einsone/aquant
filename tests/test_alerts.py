"""测试告警系统"""

from unittest.mock import Mock, patch

from aquant.live.alerts import AlertLevel, AlertManager, ConsoleAlertChannel, DingTalkAlertChannel, EmailAlertChannel, WeChatWorkAlertChannel


def test_alert_levels():
    """测试告警级别枚举"""
    assert AlertLevel.INFO == "info"
    assert AlertLevel.WARNING == "warning"
    assert AlertLevel.ERROR == "error"
    assert AlertLevel.CRITICAL == "critical"


def test_console_alert_channel():
    """测试控制台告警渠道"""
    channel = ConsoleAlertChannel()

    # 应该不抛异常
    channel.send(AlertLevel.INFO, "测试标题", "测试消息")
    channel.send(AlertLevel.WARNING, "警告", "警告消息", {"key": "value"})
    channel.send(AlertLevel.ERROR, "错误", "错误消息")
    channel.send(AlertLevel.CRITICAL, "严重", "严重消息")


@patch("smtplib.SMTP")
def test_email_alert_channel(mock_smtp):
    """测试邮件告警渠道"""
    channel = EmailAlertChannel(smtp_host="smtp.example.com", smtp_port=587, username="user@example.com", password="password", from_addr="user@example.com", to_addrs=["recipient@example.com"])

    # 模拟 SMTP 服务器
    mock_server = Mock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    channel.send(AlertLevel.ERROR, "测试错误", "这是一个测试错误")

    # 验证调用了正确的方法
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", "password")
    mock_server.send_message.assert_called_once()


@patch("smtplib.SMTP")
def test_email_alert_with_extra(mock_smtp):
    """测试带额外信息的邮件告警"""
    channel = EmailAlertChannel(smtp_host="smtp.example.com", smtp_port=587, username="user@example.com", password="password", from_addr="user@example.com", to_addrs=["recipient@example.com"])

    mock_server = Mock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    extra = {"strategy": "momentum", "loss": -5000}
    channel.send(AlertLevel.CRITICAL, "策略亏损", "策略触发止损", extra)

    mock_server.send_message.assert_called_once()


@patch("requests.post")
def test_dingtalk_alert_channel(mock_post):
    """测试钉钉告警渠道"""
    mock_response = Mock()
    mock_response.json.return_value = {"errcode": 0}
    mock_post.return_value = mock_response

    channel = DingTalkAlertChannel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx")

    channel.send(AlertLevel.WARNING, "交易提醒", "策略已开仓")

    # 验证发送了请求
    mock_post.assert_called_once()
    call_args = mock_post.call_args

    # 验证请求内容
    assert "json" in call_args.kwargs
    payload = call_args.kwargs["json"]
    assert payload["msgtype"] == "markdown"
    assert "交易提醒" in payload["markdown"]["title"]


@patch("requests.post")
def test_dingtalk_alert_with_signature(mock_post):
    """测试带签名的钉钉告警"""
    mock_response = Mock()
    mock_response.json.return_value = {"errcode": 0}
    mock_post.return_value = mock_response

    channel = DingTalkAlertChannel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx", secret="SECRET123")

    channel.send(AlertLevel.INFO, "测试", "消息")

    # 验证 URL 包含签名参数
    call_args = mock_post.call_args
    url = call_args.args[0]
    assert "timestamp=" in url
    assert "sign=" in url


@patch("requests.post")
def test_dingtalk_alert_with_extra(mock_post):
    """测试带额外信息的钉钉告警"""
    mock_response = Mock()
    mock_response.json.return_value = {"errcode": 0}
    mock_post.return_value = mock_response

    channel = DingTalkAlertChannel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx")

    extra = {"position": "000001.SZ", "shares": 1000}
    channel.send(AlertLevel.INFO, "开仓通知", "已买入股票", extra)

    # 验证额外信息被包含在消息中
    payload = mock_post.call_args.kwargs["json"]
    text = payload["markdown"]["text"]
    assert "000001.SZ" in text


@patch("requests.post")
def test_wechat_work_alert_channel(mock_post):
    """测试企业微信告警渠道"""
    mock_response = Mock()
    mock_response.json.return_value = {"errcode": 0}
    mock_post.return_value = mock_response

    channel = WeChatWorkAlertChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")

    channel.send(AlertLevel.ERROR, "系统错误", "数据库连接失败")

    # 验证发送了请求
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert payload["msgtype"] == "markdown"
    assert "系统错误" in payload["markdown"]["content"]


def test_alert_manager_init():
    """测试告警管理器初始化"""
    manager = AlertManager()

    assert len(manager.channels) == 0


def test_alert_manager_add_channel():
    """测试添加告警渠道"""
    manager = AlertManager()
    channel = ConsoleAlertChannel()

    manager.add_channel(channel)

    assert len(manager.channels) == 1
    assert manager.channels[0] == channel


def test_alert_manager_send():
    """测试发送告警"""
    manager = AlertManager()

    # 添加模拟渠道
    mock_channel1 = Mock()
    mock_channel2 = Mock()
    manager.add_channel(mock_channel1)
    manager.add_channel(mock_channel2)

    manager.send(AlertLevel.WARNING, "测试", "消息")

    # 验证所有渠道都被调用
    mock_channel1.send.assert_called_once_with(AlertLevel.WARNING, "测试", "消息", None)
    mock_channel2.send.assert_called_once_with(AlertLevel.WARNING, "测试", "消息", None)


def test_alert_manager_send_with_extra():
    """测试发送带额外信息的告警"""
    manager = AlertManager()
    mock_channel = Mock()
    manager.add_channel(mock_channel)

    extra = {"key": "value"}
    manager.send(AlertLevel.ERROR, "错误", "详情", extra)

    mock_channel.send.assert_called_once_with(AlertLevel.ERROR, "错误", "详情", extra)


def test_alert_manager_send_no_channels():
    """测试无渠道时发送告警"""
    manager = AlertManager()

    # 应该不抛异常，只记录警告
    manager.send(AlertLevel.INFO, "测试", "消息")


def test_alert_manager_send_channel_failure():
    """测试渠道发送失败"""
    manager = AlertManager()

    # 添加会失败的渠道
    mock_channel = Mock()
    mock_channel.send.side_effect = Exception("发送失败")
    manager.add_channel(mock_channel)

    # 应该捕获异常，不抛出
    manager.send(AlertLevel.ERROR, "测试", "消息")


def test_alert_manager_convenience_methods():
    """测试便捷方法"""
    manager = AlertManager()
    mock_channel = Mock()
    manager.add_channel(mock_channel)

    # info
    manager.info("信息", "详情")
    mock_channel.send.assert_called_with(AlertLevel.INFO, "信息", "详情", None)

    # warning
    manager.warning("警告", "详情")
    mock_channel.send.assert_called_with(AlertLevel.WARNING, "警告", "详情", None)

    # error
    manager.error("错误", "详情")
    mock_channel.send.assert_called_with(AlertLevel.ERROR, "错误", "详情", None)

    # critical
    manager.critical("严重", "详情")
    mock_channel.send.assert_called_with(AlertLevel.CRITICAL, "严重", "详情", None)


def test_alert_manager_multiple_channels():
    """测试多渠道告警"""
    manager = AlertManager()

    console = ConsoleAlertChannel()
    mock_email = Mock()
    mock_dingtalk = Mock()

    manager.add_channel(console)
    manager.add_channel(mock_email)
    manager.add_channel(mock_dingtalk)

    manager.error("系统异常", "详细错误信息")

    # 验证所有渠道都被调用
    mock_email.send.assert_called_once()
    mock_dingtalk.send.assert_called_once()


def test_alert_manager_partial_failure():
    """测试部分渠道失败"""
    manager = AlertManager()

    # 第一个渠道会失败
    mock_channel1 = Mock()
    mock_channel1.send.side_effect = Exception("失败")

    # 第二个渠道正常
    mock_channel2 = Mock()

    manager.add_channel(mock_channel1)
    manager.add_channel(mock_channel2)

    manager.warning("测试", "消息")

    # 第二个渠道应该仍然被调用
    mock_channel2.send.assert_called_once()
