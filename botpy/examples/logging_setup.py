# -*- coding: utf-8 -*-
"""统一日志配置。

改造前的状况：
1. 全项目只有一个 ``botpy.log``，由 botpy 的 logger 建在**当前工作目录**；
   文件没有轮转，长期跑会一直涨（已积累到 100 KB+ 的单个文件）；
2. 本程序的日志和 botpy 内部的日志混在同一个文件里，且没有请求标识——
   一次 ``/go`` 的"收消息 → 跑脚本 → 上传"在日志里串不起来；
3. 出图脚本全程 ``print``，诊断信息只能靠 client 截取 stdout 的前后几百字符，
   真出问题时关键信息已经被截掉了；
4. 日志级别、目录、大小全部写死，没法按环境调整。

这里的做法：
- **一个文件**：``<examples>/logs/bot.log``，UTF-8，按大小轮转；
- **控制台只到 WARNING**：脚本的 stderr 是 client 判断失败的依据，不能被 INFO 噪音污染；
- **请求 id**：每次处理消息开一个 context，日志行里带 ``[reqid]``，可整串追踪；
- 全部可用环境变量覆盖（``MTR_LOG_DIR`` / ``MTR_LOG_LEVEL`` / ``MTR_LOG_CONSOLE``
  / ``MTR_LOG_MAX_BYTES`` / ``MTR_LOG_BACKUPS``）；
- **建不出日志文件时降级为只输出控制台**，绝不让机器人因为日志挂了。
"""

import contextlib
import contextvars
import functools
import logging
import logging.handlers
import os
import sys
import time
import uuid

EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))

#: 默认日志目录与文件名
DEFAULT_LOG_DIR = os.path.join(EXAMPLES_DIR, "logs")
DEFAULT_LOG_FILE = "bot.log"

#: 本程序所有 logger 的根名字
ROOT_LOGGER = "mtrqqbot"

ENV_DIR = "MTR_LOG_DIR"
ENV_LEVEL = "MTR_LOG_LEVEL"
ENV_CONSOLE = "MTR_LOG_CONSOLE"
ENV_MAX_BYTES = "MTR_LOG_MAX_BYTES"
ENV_BACKUPS = "MTR_LOG_BACKUPS"

DEFAULT_LEVEL = "INFO"
DEFAULT_CONSOLE_LEVEL = "WARNING"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUPS = 5

FORMAT = (
    "%(asctime)s %(levelname)-7s [%(reqid)s] "
    "%(name)s %(filename)s:%(lineno)d %(message)s"
)
DATEFMT = "%Y-%m-%d %H:%M:%S"

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

#: 当前请求 id（协程/线程各自独立，不会被并发请求串台）
_request_id = contextvars.ContextVar("mtr_request_id", default="-")


class _RequestFilter(logging.Filter):
    """把 contextvar 里的请求 id 注进每条日志记录。"""

    def filter(self, record):
        record.reqid = _request_id.get()
        return True


def resolve_level(value, default=DEFAULT_LEVEL):
    """把 ``"info"`` / ``20`` / ``None`` 这类输入统一成 logging 级别。"""
    if value is None or value == "":
        return _LEVELS[default]
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text.isdigit():
        return int(text)
    return _LEVELS.get(text, _LEVELS[default])


def new_request_id(seed=""):
    """生成请求 id：给了种子（如 QQ 消息 id）就取尾部，否则随机。"""
    seed = str(seed or "").strip()
    if seed:
        return seed[-8:]
    return uuid.uuid4().hex[:8]


def current_request_id():
    return _request_id.get()


@contextlib.contextmanager
def request_context(seed=""):
    """给一段处理逻辑打上请求 id，退出时恢复上一层。"""
    token = _request_id.set(new_request_id(seed))
    try:
        yield _request_id.get()
    finally:
        _request_id.reset(token)


def _clear_handlers(logger):
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _build_formatter():
    return logging.Formatter(FORMAT, datefmt=DATEFMT)


def _build_file_handler(log_dir, log_file, max_bytes, backups, level):
    """建轮转文件处理器；目录不可写时返回 None（不抛异常）。"""
    path = os.path.join(log_dir, log_file)
    try:
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
    except OSError:
        return None
    handler.setLevel(level)
    handler.setFormatter(_build_formatter())
    handler.addFilter(_RequestFilter())
    return handler


def _build_console_handler(level, stream=None):
    stream = stream or sys.stderr
    # Windows 控制台默认 GBK，中文日志可能直接抛 UnicodeEncodeError
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(_build_formatter())
    handler.addFilter(_RequestFilter())
    return handler


def _merge_botpy_logger(handlers, level):
    """把 botpy 自己的日志并到同一个文件里，避免两个 ``*.log`` 各写一半。"""
    target = logging.getLogger("botpy")
    # 先摘掉它自带的 botpy.log 文件处理器（重复 setup 时也不会堆积）
    for handler in list(target.handlers):
        target.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    for handler in handlers:
        target.addHandler(handler)
    target.setLevel(level)
    target.propagate = False


def setup(level=None, console_level=None, log_dir=None, log_file=None,
          max_bytes=None, backups=None, merge_botpy=True, console_stream=None):
    """配置主程序日志：文件（轮转，UTF-8）+ 控制台。

    可重复调用：每次都会先清掉旧处理器，不会出现重复行。
    返回配置好的 logger。
    """
    level = resolve_level(
        level if level is not None else os.environ.get(ENV_LEVEL), DEFAULT_LEVEL
    )
    console_level = resolve_level(
        console_level if console_level is not None else os.environ.get(ENV_CONSOLE),
        DEFAULT_CONSOLE_LEVEL,
    )
    log_dir = log_dir or os.environ.get(ENV_DIR) or DEFAULT_LOG_DIR
    log_file = log_file or DEFAULT_LOG_FILE
    if max_bytes is None:
        max_bytes = int(os.environ.get(ENV_MAX_BYTES) or DEFAULT_MAX_BYTES)
    if backups is None:
        backups = int(os.environ.get(ENV_BACKUPS) or DEFAULT_BACKUPS)

    logger = logging.getLogger(ROOT_LOGGER)
    logger.setLevel(level)
    logger.propagate = False
    _clear_handlers(logger)

    file_handler = _build_file_handler(log_dir, log_file, max_bytes, backups, level)
    if file_handler is not None:
        logger.addHandler(file_handler)
    logger.addHandler(_build_console_handler(console_level, console_stream))

    if merge_botpy:
        _merge_botpy_logger(list(logger.handlers), level)

    if file_handler is None:
        logger.warning("日志目录不可写（%s），本次仅输出到控制台", log_dir)
    return logger


def setup_console(level=None, stream=None):
    """给独立运行的脚本用：只输出到控制台，不碰文件。

    默认 WARNING，这样被 client 以子进程调用时 stderr 保持干净
    （client 靠 stderr 判断脚本是否失败）。想看详细信息先设
    ``MTR_LOG_CONSOLE=INFO`` 或调用时传 ``level='INFO'``。
    """
    level = resolve_level(
        level if level is not None else os.environ.get(ENV_CONSOLE), DEFAULT_CONSOLE_LEVEL
    )
    logger = logging.getLogger(ROOT_LOGGER)
    logger.setLevel(level)
    logger.propagate = False
    _clear_handlers(logger)
    logger.addHandler(_build_console_handler(level, stream))
    return logger


def get_logger(name=None):
    """取 ``mtrqqbot.*`` 下的 logger；不负责配置处理器。"""
    if not name:
        return logging.getLogger(ROOT_LOGGER)
    if name.startswith(ROOT_LOGGER + "."):
        return logging.getLogger(name)
    return logging.getLogger("%s.%s" % (ROOT_LOGGER, name))


def log_file_path(log_dir=None, log_file=None):
    """当前（或指定）日志文件路径，测试与排障用。"""
    log_dir = log_dir or os.environ.get(ENV_DIR) or DEFAULT_LOG_DIR
    return os.path.join(log_dir, log_file or DEFAULT_LOG_FILE)


def _sender_info(message):
    """尽量从 botpy 的 GroupMessage 里挖出群号和提问者，取不到就返回 '-'。"""
    group = getattr(message, "group_openid", None) or "-"
    author = getattr(message, "author", None)
    user = (
        getattr(author, "member_openid", None)
        or getattr(author, "id", None)
        or "-"
    )
    return group, user


def traced(handler):
    """给 ``async def 处理器(self, message)`` 套上请求上下文与耗时统计。

    这样一个 /go 指令在日志里就是同一个 ``[reqid]`` 下的完整链路：
    收到消息 → 执行脚本 → 上传图片 → 处理结束（含总耗时）。
    """

    @functools.wraps(handler)
    async def wrapper(*args, **kwargs):
        message = kwargs.get("message")
        if message is None and len(args) >= 2:
            message = args[1]

        seed = getattr(message, "id", "") or ""
        group, user = _sender_info(message)
        logger = get_logger(handler.__name__)
        started = time.perf_counter()

        with request_context(seed):
            logger.info("收到消息 msg_id=%s group=%s user=%s", seed or "-", group, user)
            try:
                return await handler(*args, **kwargs)
            except Exception:
                logger.exception("处理消息抛出异常 handler=%s", handler.__name__)
                raise
            finally:
                logger.info(
                    "消息处理结束 耗时=%.0fms", (time.perf_counter() - started) * 1000
                )

    return wrapper
