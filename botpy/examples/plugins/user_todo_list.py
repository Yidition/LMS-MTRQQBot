# -*- coding: utf-8 -*-
"""按用户 openid 存放待办事项的 JSON 小工具。

历史 bug：目录被写死成 ``'..\\examples\\user_data\\'``。从 examples 目录
（也就是 README 要求的启动目录）运行时，这个相对路径会被解析成
``<项目>/examples/user_data/`` —— 一个根本不存在的目录，于是所有待办功能
（包括新建文件）都会直接 FileNotFoundError。

现在目录基于 ``__file__`` 计算，可用 ``MTR_USER_DATA_DIR`` 环境变量覆盖（便于测试），
并且任何一次读写前都会自动创建目录。
"""

import json
import os

#: 待办 JSON 的存放目录
DATA_DIR = os.path.abspath(
    os.environ.get("MTR_USER_DATA_DIR")
    or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user_data")
)

#: 列表为空时的占位文案
EMPTY_HINT = "还没有待办qwq"


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR


def _user_path(user_name):
    """拼出某个用户的 JSON 路径，并清洗文件名（openid 里不该出现路径分隔符）。"""
    safe = str(user_name or "").strip().replace("/", "_").replace("\\", "_")
    if not safe:
        raise ValueError("user_name 不能为空")
    return os.path.join(_ensure_dir(), safe + ".json")


def _clean(todos):
    """过滤掉历史遗留的空白占位项。

    老版本创建用户文件时会写入 ``[占位文案, ' ']``，那个 ``' '`` 会占掉一个
    序号，导致 delete(1) 删到的是空格而不是第一条待办。
    """
    return [str(item) for item in (todos or []) if str(item).strip()]


def _read(user_name):
    """读取待办列表；文件不存在返回 None。"""
    path = _user_path(user_name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return []
    return _clean(data.get("ToDo"))


def _write(user_name, todos):
    path = _user_path(user_name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"ToDo": list(todos)}, handle, ensure_ascii=False, indent=2)
    return path


def show(user_name):
    """返回该用户的待办列表；文件不存在时创建并返回 -1。"""
    todos = _read(user_name)
    if todos is None:
        return file_not_found(DATA_DIR, user_name)
    return todos


def insert(user_name, todo):
    """追加一条待办，返回 1；用户文件不存在时创建并返回 -1。"""
    todos = _read(user_name)
    if todos is None:
        return file_not_found(DATA_DIR, user_name)

    # 原来的实现用 in-place clear()，会把调用方持有的列表也清掉
    todo = "" if todo is None else str(todo)
    cleaned = [item for item in todos if item != EMPTY_HINT]
    cleaned.append(todo)
    _write(user_name, cleaned)
    return 1


def delete(user_name, num):
    """删除第 ``num`` 条待办（1 基），返回 1。

    列表删空后写回占位文案，而不是像以前那样把整张表重置。
    越界返回 -2，用户文件不存在返回 -1。
    """
    todos = _read(user_name)
    if todos is None:
        return file_not_found(DATA_DIR, user_name)

    if todos == [EMPTY_HINT]:
        print("[Warning] ToDo list is empty, nothing to delete.")
        return -2

    try:
        index = int(num)
    except (TypeError, ValueError):
        return -2
    if index < 1 or index > len(todos):
        print("[Warning] List length out of range.")
        return -2

    todos.pop(index - 1)
    _write(user_name, todos or [EMPTY_HINT])
    return 1


def init(user_name):
    """把该用户的待办重置为空，返回 1；文件不存在时创建并返回 -1。"""
    print("[Warning] Initializing ToDo List of '%s'" % user_name)
    if _read(user_name) is None:
        return file_not_found(DATA_DIR, user_name)
    _write(user_name, [EMPTY_HINT])
    print("'%s' initialized." % _user_path(user_name))
    return 1


def file_not_found(base_dir, user_name):
    """用户文件不存在时创建它，并返回 -1（保持原有返回值约定）。"""
    path = _user_path(user_name)
    print("[Warning] File '%s' not found" % path)
    print("[Info] Creating file '%s'" % path)
    _write(user_name, [EMPTY_HINT])
    return -1
