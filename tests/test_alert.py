"""告警模块测试"""

from aquant.alert import AlertLevel, DingTalkChannel, EmailChannel, Notifier, WeComChannel


def test_notifier_basic():
    """测试基本告警功能"""
    notifier = Notifier(min_level=AlertLevel.WARNING)

    # 不添加渠道，应该返回 False
    assert not notifier.send("测试消息", level=AlertLevel.ERROR)

    # 添加一个模拟渠道
    class MockChannel:
        def __init__(self):
            self.messages = []

        def send(self, message: str, level: AlertLevel) -> bool:
            self.messages.append((message, level))
            return True

    mock_channel = MockChannel()
    notifier.add_channel(mock_channel)

    # 发送消息
    assert notifier.send("错误消息", level=AlertLevel.ERROR)
    assert len(mock_channel.messages) == 1
    assert "错误消息" in mock_channel.messages[0][0]
    assert mock_channel.messages[0][1] == AlertLevel.ERROR


def test_notifier_level_filter():
    """测试告警级别过滤"""

    class MockChannel:
        def __init__(self):
            self.messages = []

        def send(self, message: str, level: AlertLevel) -> bool:
            self.messages.append((message, level))
            return True

    mock_channel = MockChannel()
    notifier = Notifier(min_level=AlertLevel.WARNING)
    notifier.add_channel(mock_channel)

    # INFO 级别应该被过滤
    notifier.send("信息", level=AlertLevel.INFO)
    assert len(mock_channel.messages) == 0

    # WARNING 及以上应该发送
    notifier.send("警告", level=AlertLevel.WARNING)
    notifier.send("错误", level=AlertLevel.ERROR)
    assert len(mock_channel.messages) == 2


def test_notifier_context():
    """测试附加上下文"""

    class MockChannel:
        def __init__(self):
            self.messages = []

        def send(self, message: str, level: AlertLevel) -> bool:
            self.messages.append(message)
            return True

    mock_channel = MockChannel()
    notifier = Notifier()
    notifier.add_channel(mock_channel)

    # 发送带上下文的消息
    notifier.send("风控触发", level=AlertLevel.ERROR, position="000001.SZ", weight=0.5)

    assert len(mock_channel.messages) == 1
    message = mock_channel.messages[0]
    assert "风控触发" in message
    assert "position: 000001.SZ" in message
    assert "weight: 0.5" in message


def test_multiple_channels():
    """测试多渠道通知"""

    class MockChannel1:
        def send(self, message: str, level: AlertLevel) -> bool:
            return True

    class MockChannel2:
        def send(self, message: str, level: AlertLevel) -> bool:
            return False  # 模拟失败

    class MockChannel3:
        def send(self, message: str, level: AlertLevel) -> bool:
            return True

    notifier = Notifier()
    notifier.add_channel(MockChannel1())
    notifier.add_channel(MockChannel2())
    notifier.add_channel(MockChannel3())

    # 至少一个成功就返回 True
    assert notifier.send("测试", level=AlertLevel.INFO)


def test_dingtalk_channel_structure():
    """测试钉钉渠道结构（不实际发送）"""
    channel = DingTalkChannel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test", secret=None)

    assert channel.webhook_url
    assert channel.secret is None


def test_wecom_channel_structure():
    """测试企业微信渠道结构（不实际发送）"""
    channel = WeComChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")

    assert channel.webhook_url


def test_email_channel_structure():
    """测试邮件渠道结构（不实际发送）"""
    channel = EmailChannel(smtp_host="smtp.gmail.com", smtp_port=587, username="test@example.com", password="password", from_addr="test@example.com", to_addrs=["alert@example.com"])

    assert channel.smtp_host == "smtp.gmail.com"
    assert channel.smtp_port == 587
    assert channel.from_addr == "test@example.com"
    assert "alert@example.com" in channel.to_addrs
