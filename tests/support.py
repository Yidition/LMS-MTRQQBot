# -*- coding: utf-8 -*-
"""测试公共设施：定位 examples 目录、准备可写工作区、给 botpy 打桩。"""

import os
import shutil
import sys
import tempfile
import types

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
EXAMPLES_DIR = os.path.join(PROJECT_DIR, "botpy", "examples")

#: 项目脚本里写死的本地地图服务地址，缓存文件名由它的 md5 决定
LINK = "http://localhost:1025"
LINK_HASH = "1bb6987c13cf561edb12699724a8f64f"

CACHE_FILES = (
    "mtr-original-data-%s-mtr4-v4.json" % LINK_HASH,
    "mtr-route-departure-%s-mtr4-v4.json" % LINK_HASH,
)

_workspace = None


def ensure_examples_on_path():
    if EXAMPLES_DIR not in sys.path:
        sys.path.insert(0, EXAMPLES_DIR)


def child_env():
    """和 client.py 一致的子进程环境（强制 UTF-8）。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def workspace():
    """准备一个可写的仿真工作目录，返回路径（进程内只建一次）。

    脚本全部使用相对 cwd 的路径（mtr_pathfinder_data / 缓存 json /
    mtr_pathfinder_temp），所以要测试它们就必须给一个既能读数据、又能写产物的目录。
    """
    global _workspace
    if _workspace is not None:
        return _workspace

    work = tempfile.mkdtemp(prefix="mtrqqbot-test-")
    for name in CACHE_FILES:
        source = os.path.join(EXAMPLES_DIR, name)
        if not os.path.isfile(source):
            raise RuntimeError("测试需要缓存数据文件：%s" % source)
        shutil.copy2(source, os.path.join(work, name))

    shutil.copytree(
        os.path.join(EXAMPLES_DIR, "mtr_pathfinder_data"),
        os.path.join(work, "mtr_pathfinder_data"),
    )

    # 出图脚本会把本目录注册进 DLL 搜索路径（raqm_support.py），
    # 复制脚本到工作区时这两个 DLL 必须一起过去，否则渲染会报
    # "not supported without libraqm"
    for name in ("libraqm.dll", "fribidi-0.dll"):
        source = os.path.join(EXAMPLES_DIR, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(work, name))

    _workspace = work
    return work


def cleanup_workspace():
    global _workspace
    if _workspace:
        shutil.rmtree(_workspace, ignore_errors=True)
        _workspace = None


def stub_botpy():
    """给没装 qq-botpy 的环境造一个最小替身，只为能 import 插件。

    插件真正需要的只有 ``botpy.ext.cog_yaml.read``。
    """
    import yaml

    def read(path):
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    botpy = types.ModuleType("botpy")
    ext = types.ModuleType("botpy.ext")
    cog_yaml = types.ModuleType("botpy.ext.cog_yaml")
    cog_yaml.read = read

    botpy.ext = ext
    ext.cog_yaml = cog_yaml

    sys.modules.setdefault("botpy", botpy)
    sys.modules.setdefault("botpy.ext", ext)
    sys.modules.setdefault("botpy.ext.cog_yaml", cog_yaml)
