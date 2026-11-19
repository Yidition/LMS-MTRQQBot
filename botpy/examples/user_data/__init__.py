# -*- coding: utf-8 -*-
"""把所有用户待办一键重置为空。

历史 bug：``base_dir = ''`` 让 ``os.listdir('')`` 直接 FileNotFoundError；
而且它会尝试把目录下**所有**文件都当 JSON 覆盖（包括 ``__init__.py``）。
现在只处理同目录的 ``*.json``，路径基于 ``__file__``。

Reset every user's to-do list to empty in one go.

Historical bug: ``base_dir = ''`` made ``os.listdir('')`` raise
FileNotFoundError outright, and it also tried to overwrite **every** file in the
directory as JSON (including ``__init__.py``). It now touches only ``*.json`` in
the same directory, with paths based on ``__file__``.
"""

import json
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EMPTY_HINT = "还没有待办qwq"

if __name__ == "__main__":
    print("[Warning] Initializing all user ToDo lists.")
    print("\n[Warning] Do you wish to continue?[Y/N]")
    flag = input()

    if flag in ("Y", "y"):
        count = 0
        for name in sorted(os.listdir(DATA_DIR)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(DATA_DIR, name)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"ToDo": [EMPTY_HINT]}, handle, ensure_ascii=False, indent=2)
            print("'%s' initialized." % path)
            count += 1
        print("\n[Info] ***Initialization Complete*** (%d file(s))" % count)
    elif flag in ("N", "n"):
        print("[Info] Initialization aborted.")
    else:
        print("[Warning] Illegal argument, process finished.")
