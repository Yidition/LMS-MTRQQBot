# -*- coding: utf-8 -*-
"""client.py 的纯逻辑部分：命令解析、子进程命令构造、脚本输出判定。

这些逻辑以前全写在 ``client.py`` 里，而 ``client.py`` 一开头就 ``import botpy``，
导致没有装 botpy 的环境根本没法测。把不依赖网络/机器人框架的部分抽到这里，
就可以直接写单元测试覆盖。

本模块刻意只依赖标准库。
"""

import os
import re
import sys

#: examples 目录（本文件所在目录），所有脚本与资源路径都以它为基准
EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))

#: 外部脚本默认超时（秒）
SCRIPT_TIMEOUT = 180

#: 匹配 --no-xxx 形式的寻路参数
NO_OPTION_RE = re.compile(r"--no-[^\s]+")

USAGE_ROUTE = "格式：/go 或 /路线 [起点];[终点] [可选参数]\n可选参数：--no-highspeed, --no-lightrail, --no-[线路名]"

SEMICOLON_HINT = "格式不正确，请使用英文分号';'分隔起点和终点。\n例如：/go Badland;Glass --no-highspeed"

#: 命令表：按顺序匹配，长/具体的放前面。第二个元素是命令前缀。
COMMANDS = (
    ("ping", "/ping"),
    ("secret", "/secret"),
    ("ds-think", "/ds-think"),
    ("xjy", "/xjy"),
    ("ban", "/ban"),
    ("jam", "/jam"),
    ("lps", "/lps"),
    ("timetable", "/时刻表"),
    ("diagram", "/运行图"),
    ("route", "/go"),
    ("route", "/路线"),
)

#: 直接回文本的整活指令
CHITCHAT_COMMANDS = ("ping", "secret", "ds-think", "xjy", "ban", "jam", "lps")


def split_no_options(message):
    """把 ``--no-xxx`` 参数从消息里剥出来。

    返回 ``(清理后的消息, 传给寻路脚本的参数列表)``。

    ``--no-highspeed`` / ``--no-lightrail`` 原样保留，
    其它 ``--no-线路名`` 会展开成 ``--no-line 线路名``。
    """
    message = message or ""
    args = []
    for option in NO_OPTION_RE.findall(message):
        if option in ("--no-highspeed", "--no-lightrail"):
            args.append(option)
        else:
            args.extend(["--no-line", option[len("--no-"):]])

    return NO_OPTION_RE.sub("", message).strip(), args


def match_command(text):
    """识别命令，返回 ``(命令名, 该命令之后的文本)``；无法识别时返回 ``(None, '')``。

    ASCII 命令要求前缀后面紧跟空白或字符串结尾，避免 ``/go`` 误吞 ``/google``。
    """
    text = (text or "").strip()
    for name, prefix in COMMANDS:
        if not text.startswith(prefix):
            continue
        rest = text[len(prefix):]
        # 前缀以字母数字结尾时要求词边界
        if prefix[-1].isascii() and prefix[-1].isalnum():
            if rest and not rest[0].isspace():
                continue
        return name, rest.strip()
    return None, ""


def parse_route_request(rest):
    """解析 ``起点;终点``，返回 ``{'ok': True, 'start': ..., 'end': ...}`` 或错误信息。"""
    rest = (rest or "").strip()
    if not rest:
        return {"ok": False, "error": USAGE_ROUTE}

    index = rest.find(";")
    if index == -1:
        return {"ok": False, "error": SEMICOLON_HINT}

    start = rest[:index].strip()
    end = rest[index + 1:].strip()
    if not start or not end:
        return {"ok": False, "error": "起点或终点不能为空！"}
    if start == end:
        return {"ok": False, "error": "起始站和终点站不能相同！"}
    return {"ok": True, "start": start, "end": end}


def python_executable():
    """挑一个解释器来跑外部脚本。

    优先 ``MTR_PYTHON`` 环境变量，其次当前解释器。**不能用 ``py``**：
    它指向的是 py launcher 的默认版本，和跑机器人的解释器很可能不是同一个，
    缺依赖时会直接 ModuleNotFoundError。
    """
    override = os.environ.get("MTR_PYTHON")
    if override:
        return override
    return sys.executable


def build_script_command(script, *args, **kwargs):
    """构造执行脚本的完整命令行。

    ``-B`` 保证不写 ``__pycache__``，避免在只读目录下跑不起来。
    """
    python = kwargs.pop("python", None)
    if kwargs:
        raise TypeError("unexpected kwargs: %r" % (sorted(kwargs),))

    exe = python or python_executable()
    path = script if os.path.isabs(script) else os.path.join(EXAMPLES_DIR, script)
    return [exe, "-B", path] + [str(a) for a in args]


def child_env():
    """子进程环境：强制 UTF-8，避免 GBK 输出被按 UTF-8 解码时炸掉。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def interpret_result(stdout, stderr, returncode=None):
    """判断脚本是否成功，返回 ``(是否成功, 错误摘要)``。

    成功契约：脚本在 stdout 打印 ``SUCCESS:<路径>``。
    失败时优先用 stderr（traceback 更有价值），没有就退回 stdout。
    """
    stdout = stdout or ""
    stderr = stderr or ""

    if "SUCCESS" in stdout:
        return True, ""

    message = stderr.strip() or stdout.strip()
    if not message:
        message = "脚本没有任何输出"
        if returncode is not None:
            message += "（返回码 %s）" % returncode

    # 去掉脚本固定打印的 FAILED 噪音行
    lines = [line for line in message.splitlines() if line.strip() and line.strip() != "FAILED"]
    message = "\n".join(lines) or "脚本执行失败（无详细信息）"
    return False, message[-300:]
