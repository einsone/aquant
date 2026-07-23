# 告警通知使用指南

Aquant 提供了灵活的告警通知系统，支持多种通知渠道。

## 快速开始

### 基本使用

```python
from aquant.alert import Notifier, AlertLevel, DingTalkChannel

# 创建通知器
notifier = Notifier(min_level=AlertLevel.WARNING)

# 添加钉钉渠道
notifier.add_channel(
    DingTalkChannel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx")
)

# 发送告警
notifier.send("风控触发：持仓超过限制", level=AlertLevel.ERROR, position="000001.SZ")
```

## 告警级别

Aquant 支持四个告警级别：

- `AlertLevel.INFO` - 信息
- `AlertLevel.WARNING` - 警告
- `AlertLevel.ERROR` - 错误
- `AlertLevel.CRITICAL` - 严重

通知器可以设置最低级别，低于该级别的告警会被过滤。

## 支持的通知渠道

### 1. 钉钉机器人

```python
from aquant.alert import DingTalkChannel

# 不加签
channel = DingTalkChannel(
    webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx"
)

# 加签（推荐）
channel = DingTalkChannel(
    webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
    secret="SECxxxxxxxxxxxxxxxxxxxx"
)

notifier.add_channel(channel)
```

**获取钉钉机器人 Webhook：**
1. 在钉钉群中添加自定义机器人
2. 选择"自定义关键词"或"加签"安全设置
3. 复制 Webhook URL 和密钥

### 2. 企业微信机器人

```python
from aquant.alert import WeComChannel

channel = WeComChannel(
    webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
)

notifier.add_channel(channel)
```

**获取企业微信机器人 Webhook：**
1. 在企业微信群中添加群机器人
2. 复制 Webhook 地址

### 3. 邮件通知

```python
from aquant.alert import EmailChannel

channel = EmailChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your@gmail.com",
    password="your_app_password",  # Gmail 需要使用应用专用密码
    from_addr="your@gmail.com",
    to_addrs=["alert@company.com", "admin@company.com"]
)

notifier.add_channel(channel)
```

**Gmail 配置：**
1. 启用两步验证
2. 生成应用专用密码
3. 使用应用密码而非账号密码

## 在实盘交易中使用

```python
from aquant.alert import Notifier, AlertLevel, DingTalkChannel
from aquant.live import LiveTradingEngine

# 创建通知器
notifier = Notifier(min_level=AlertLevel.WARNING)
notifier.add_channel(DingTalkChannel(webhook_url="..."))

# 传递给实盘引擎
engine = LiveTradingEngine(
    strategy=strategy,
    broker=broker,
    data_source=data_source,
    notifier=notifier  # 传入通知器
)

# 引擎会在以下情况发送告警：
# - 交易执行失败（ERROR 级别）
# - 风控触发（WARNING 级别）
# - 系统异常（CRITICAL 级别）
```

## 多渠道通知

可以同时添加多个通知渠道，告警会发送到所有渠道：

```python
notifier = Notifier(min_level=AlertLevel.WARNING)

# 添加钉钉
notifier.add_channel(DingTalkChannel(webhook_url="..."))

# 添加企业微信
notifier.add_channel(WeComChannel(webhook_url="..."))

# 添加邮件
notifier.add_channel(EmailChannel(
    smtp_host="smtp.gmail.com",
    smtp_port=587,
    username="your@gmail.com",
    password="your_app_password",
    from_addr="your@gmail.com",
    to_addrs=["alert@company.com"]
))

# 告警会同时发送到所有渠道
notifier.send("严重错误", level=AlertLevel.CRITICAL)
```

## 自定义通知渠道

可以实现 `Channel` 协议来添加自定义渠道：

```python
from aquant.alert import AlertLevel

class CustomChannel:
    def send(self, message: str, level: AlertLevel) -> bool:
        """发送通知"""
        # 实现你的通知逻辑
        print(f"[{level.name}] {message}")
        return True

notifier.add_channel(CustomChannel())
```

## 附加上下文信息

可以在发送告警时附加上下文信息：

```python
notifier.send(
    "风控触发",
    level=AlertLevel.ERROR,
    position="000001.SZ",
    target_weight=0.3,
    current_weight=0.5,
    reason="超过最大持仓限制"
)
```

上下文信息会自动格式化并附加到告警消息中。

## 最佳实践

1. **设置合适的最低级别**：生产环境建议使用 `AlertLevel.WARNING`，避免信息过载
2. **使用加签**：钉钉机器人建议启用加签功能，提高安全性
3. **多渠道冗余**：重要告警建议配置多个渠道，避免单点故障
4. **附加上下文**：告警时附加足够的上下文信息，便于快速定位问题
5. **测试告警**：上线前测试所有告警渠道是否正常工作

## 故障排查

### 钉钉机器人无响应
- 检查 Webhook URL 是否正确
- 检查安全设置（关键词或加签）
- 查看钉钉机器人管理页面的错误日志

### Gmail 发送失败
- 确认已启用两步验证
- 使用应用专用密码，而非账号密码
- 检查 SMTP 服务器和端口配置

### 企业微信无响应
- 检查 Webhook URL 是否正确
- 确认机器人未被禁用
- 查看企业微信管理后台的日志
