# -*- coding: utf-8 -*-
"""让 Pillow 找到随项目携带的 libraqm / fribidi DLL。

Pillow 的复杂文本排版能力（`ImageDraw.text` 的 ``direction`` / ``language`` /
``features`` 参数）依赖 libraqm。本项目把 ``libraqm.dll`` 和它依赖的
``fribidi-0.dll`` 放在 examples 目录下，但 Windows 默认不会搜索"脚本所在目录"，
所以只要当前工作目录不是 examples，`PIL.features.check('raqm')` 就返回 False，
之后每次出图都会抛：

    ValueError: setting text direction, language or font features is not
    supported without libraqm

实测三种方案（Pillow 10.4 / Python 3.8）：

    os.add_dll_directory(...)   → 无效，Pillow 内部用的是普通 LoadLibrary
    把目录塞进 PATH             → 有效，但会污染全局环境变量
    ctypes 以绝对路径预加载     → 有效，且只影响当前进程  ← 本模块采用

预加载后这两个模块已经驻留在进程里，Pillow 之后按文件名 LoadLibrary 时会直接
命中，不再依赖任何搜索路径。

**必须在 `from PIL import ...` 之前导入**：

    import raqm_support  # noqa: F401
    from PIL import Image, ImageDraw, ImageFont

Make Pillow find the libraqm / fribidi DLLs shipped with the project.

Pillow's complex text shaping (the ``direction`` / ``language`` / ``features``
arguments of `ImageDraw.text`) depends on libraqm. This project ships
``libraqm.dll`` and its dependency ``fribidi-0.dll`` in the examples directory,
but Windows does not search the "script's own directory" by default, so whenever
the current working directory is not examples, `PIL.features.check('raqm')`
returns False and every render raises:

    ValueError: setting text direction, language or font features is not
    supported without libraqm

Three approaches were measured (Pillow 10.4 / Python 3.8):

    os.add_dll_directory(...)   → no effect, Pillow uses plain LoadLibrary internally
    adding the directory to PATH → works, but pollutes a global environment variable
    ctypes preload by absolute path → works, and affects only this process  ← used here

Once preloaded, both modules already reside in the process, so Pillow's later
LoadLibrary by file name hits them directly and needs no search path.

**Must be imported before `from PIL import ...`**:

    import raqm_support  # noqa: F401
    from PIL import Image, ImageDraw, ImageFont
"""

import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

#: 预加载成功的 DLL 路径
#: Paths of the DLLs preloaded successfully.
loaded = []

#: WinDLL 句柄必须保持引用，否则模块可能被卸载
#: WinDLL handles must stay referenced, otherwise the module may be unloaded.
_handles = []


def _preload() -> None:
    if os.name != "nt":
        return
    import ctypes

    # 先加载 fribidi：libraqm 依赖它
    # Load fribidi first: libraqm depends on it.
    for name in ("fribidi-0.dll", "libraqm.dll"):
        path = os.path.join(_THIS_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            _handles.append(ctypes.WinDLL(path))
            loaded.append(path)
        except OSError:
            # 位数不匹配或依赖缺失，交给 Pillow 报错
            # Bitness mismatch or a missing dependency; let Pillow report the error.
            pass


def raqm_available() -> bool:
    """Pillow 是否能使用 libraqm（未安装 Pillow 时返回 False）。 / Whether Pillow can use libraqm (returns False when Pillow is not installed)."""
    try:
        from PIL import features
    except ImportError:
        return False
    try:
        return bool(features.check("raqm"))
    except Exception:
        return False


_preload()
