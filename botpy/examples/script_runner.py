# -*- coding: utf-8 -*-
"""执行外部出图/寻路脚本，并把过程完整写进日志。

单独成模块的原因：``client.py`` 一开头就 ``import botpy``，没有 botpy 的环境
根本没法 import，这段"跑子进程 + 打日志"的逻辑也就无法被测试覆盖。
抽出来之后它只依赖标准库和 ``bot_commands``，可以真刀真枪地跑一次出图脚本。

Run external rendering/pathfinding scripts and log the whole process.

Why this is a separate module: ``client.py`` starts with ``import botpy``, so environments
without botpy cannot import it, which left the "run a subprocess and log it" logic
untestable. Once extracted, it depends only on the standard library and ``bot_commands``,
so a rendering script can be executed for real.
"""

import asyncio
import subprocess
import time

import bot_commands as cmds
import logging_setup

_log = logging_setup.get_logger("script_runner")


async def run_script(script, *args, timeout=cmds.SCRIPT_TIMEOUT):
    """在线程池里执行寻路/出图脚本，返回 CompletedProcess；超时返回 None。

    为什么不用 ``asyncio.create_subprocess_exec``：它在 Windows 的
    ``SelectorEventLoop`` 上是 NotImplementedError，而 botpy 内部用哪种
    event loop 我们控制不了。放到线程池里跑 ``subprocess.run`` 则任何 loop 都能用，
    同时不会像原来的同步调用那样把整个机器人卡死。

    脚本的 cwd 固定为 examples 目录；环境里强制 UTF-8 —— 子进程默认按 GBK
    输出中文，原来 client.py 按 UTF-8 解码会抛 UnicodeDecodeError，
    导致所有指令都回"系统执行出错"。

    Run the pathfinding/rendering script in a thread pool and return CompletedProcess;
    return None on timeout.

    Why not ``asyncio.create_subprocess_exec``: it raises NotImplementedError on the Windows
    ``SelectorEventLoop``, and we cannot control which event loop botpy uses internally.
    Running ``subprocess.run`` in a thread pool works with any loop, and unlike the original
    synchronous call it does not freeze the whole bot.

    The script cwd is fixed to the examples directory, and the environment forces UTF-8:
    subprocesses emit Chinese in GBK by default, and the old client.py decoded it as UTF-8,
    which raised UnicodeDecodeError and made every command reply "system execution error".
    """
    cmd = cmds.build_script_command(script, *args)
    _log.info("执行外部脚本 script=%s args=%s", script, args)
    _log.debug("完整命令行: %s", subprocess.list2cmdline(cmd))

    def _call():
        return subprocess.run(
            cmd,
            cwd=cmds.EXAMPLES_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=cmds.child_env(),
            timeout=timeout,
        )

    loop = asyncio.get_event_loop()
    started = time.perf_counter()
    try:
        result = await loop.run_in_executor(None, _call)
    except subprocess.TimeoutExpired:
        elapsed = (time.perf_counter() - started) * 1000
        _log.error("外部脚本超时 script=%s timeout=%ss 已耗时=%.0fms", script, timeout, elapsed)
        return None

    elapsed = (time.perf_counter() - started) * 1000
    _log.info(
        "脚本结束 script=%s rc=%s 耗时=%.0fms stdout=%dB stderr=%dB",
        script, result.returncode, elapsed, len(result.stdout or ""), len(result.stderr or ""),
    )
    # 成功时也把原始输出留在 DEBUG 里：出图脚本的诊断信息只在这里完整保留，
    # 回给用户的消息会被截断（见 bot_commands.interpret_result）
    # Keep the raw output in DEBUG even on success: the diagnostic information of rendering
    # scripts survives only here, since the message sent to users is truncated (see
    # bot_commands.interpret_result).
    if result.stdout:
        _log.debug("stdout of %s:\n%s", script, result.stdout)
    if result.stderr:
        _log.debug("stderr of %s:\n%s", script, result.stderr)
    if result.returncode not in (0, None) and "SUCCESS" not in (result.stdout or ""):
        _log.error("脚本以非 0 退出 script=%s rc=%s", script, result.returncode)
    return result
