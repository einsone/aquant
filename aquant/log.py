"""结构化日志模块

基于 structlog 实现, 兼容标准库 logging.
首次 import 自动以默认配置初始化, 无需手动调用 setup_logging().

环境变量配置：
    AQUANT_LOG_LEVEL: 日志级别 (DEBUG/INFO/WARNING/ERROR), 默认 INFO
    AQUANT_LOG_FORMAT: 日志格式 (json/logfmt), 默认 logfmt
    AQUANT_LOG_ENV: 运行环境 (dev/prod), 默认 dev

Usage:
    from aquant.log import get_logger

    log = get_logger(__name__)
    log.info("request started", method="GET", path="/api")
"""

import logging
import os
import sys
from enum import StrEnum
from typing import Any

import structlog
from structlog.types import Processor


_configured = False


class Env(StrEnum):
    DEV = "dev"
    PROD = "prod"


class LogFormat(StrEnum):
    JSON = "json"
    LOGFMT = "logfmt"


def _get_renderer(fmt: LogFormat, *, is_dev: bool, colors: bool = True) -> Processor:
    """根据格式和环境返回对应的渲染器.

    dev  → ConsoleRenderer (人类可读)
    prod → LogfmtRenderer / JSONRenderer (机器可解析)
    """
    if fmt == LogFormat.JSON:
        return structlog.processors.JSONRenderer()
    if is_dev:
        return structlog.dev.ConsoleRenderer(colors=colors)
    return structlog.processors.LogfmtRenderer(sort_keys=True, key_order=["timestamp", "level", "event"])


def _get_shared_processors() -> list[Processor]:
    """获取共享的处理器链 (structlog 和 logging 通用)"""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder([structlog.processors.CallsiteParameter.FILENAME, structlog.processors.CallsiteParameter.FUNC_NAME, structlog.processors.CallsiteParameter.LINENO]),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def setup_logging(*, env: Env | str = Env.DEV, fmt: LogFormat | str = LogFormat.LOGFMT, level: int | str = logging.INFO) -> None:
    """配置日志系统.

    Args:
        env: 运行环境, "dev" 或 "prod"
        fmt: 日志格式, "json" 或 "logfmt"
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR 或对应的整数)
    """
    env = Env(env) if isinstance(env, str) else env
    fmt = LogFormat(fmt) if isinstance(fmt, str) else fmt
    if isinstance(level, str):
        level = logging.getLevelNamesMapping()[level.upper()]

    is_dev = env == Env.DEV
    use_colors = is_dev and sys.stderr.isatty()

    shared_processors = _get_shared_processors()

    # structlog 使用标准库 logging 作为后端, 统一日志出口
    stdlib_processors: list[Processor] = [*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter]

    structlog.configure(processors=stdlib_processors, wrapper_class=structlog.stdlib.BoundLogger, context_class=dict, logger_factory=structlog.stdlib.LoggerFactory(), cache_logger_on_first_use=True)

    # 配置标准库 logging handler
    _setup_stdlib_handler(level=level, shared_processors=shared_processors, fmt=fmt, colors=use_colors, is_dev=is_dev)


def _setup_stdlib_handler(*, level: int, shared_processors: list[Processor], fmt: LogFormat, colors: bool, is_dev: bool) -> None:
    """配置标准库 logging 的 handler 和 formatter"""
    if is_dev:
        # 更友好的异常输出
        final_processors: list[Processor] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta, _get_renderer(fmt, is_dev=True, colors=colors)]
    else:
        # 异常作为结构化字段
        final_processors = [structlog.stdlib.ProcessorFormatter.remove_processors_meta, structlog.processors.dict_tracebacks, _get_renderer(fmt, is_dev=False)]

    formatter = structlog.stdlib.ProcessorFormatter(foreign_pre_chain=[structlog.stdlib.ExtraAdder(), *shared_processors], processors=final_processors)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """获取 logger 实例

    Args:
        name: logger 名称, 通常传入 __name__
        **initial_context: 初始上下文字段
    """
    log = structlog.get_logger(name)
    if initial_context:
        log = log.bind(**initial_context)
    return log


def bind_contextvars(**context: Any) -> None:
    """绑定上下文变量 (线程/协程安全, 自动传播)

    Usage:
        bind_contextvars(request_id="abc-123", user_id=42)
        log.info("processing")  # 自动携带上下文
    """
    structlog.contextvars.bind_contextvars(**context)


def clear_contextvars() -> None:
    """清除所有上下文变量"""
    structlog.contextvars.clear_contextvars()


# 首次 import 时自动配置 (默认值), 后续 import 不重复执行
if not _configured:
    # 从环境变量读取配置
    log_level = os.environ.get("AQUANT_LOG_LEVEL", "INFO").upper()
    log_format = os.environ.get("AQUANT_LOG_FORMAT", "logfmt").lower()
    log_env = os.environ.get("AQUANT_LOG_ENV", "dev").lower()

    setup_logging(env=log_env, fmt=log_format, level=log_level)

    # httpx 日志过于频繁, 仅保留 WARNING 及以上
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _configured = True
