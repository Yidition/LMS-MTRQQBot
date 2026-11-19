# 第三方组件与来源声明

> 中文 · [English](THIRD-PARTY-NOTICES.en.md)

本文件记录本项目（MTR 寻路 Bot）的来源、修改情况，以及随仓库分发的第三方组件。
项目整体以 **GPL-3.0-only** 授权，全文见 [LICENSE](LICENSE)。

---

## 一、上游作品与修改声明

依据 GPLv3 第 5(a) 条：本项目**修改过**上游作品，特此声明。

本项目的衍生链为：

```
CokeStudios/mtr-pathfinder  (GPL-3.0)
        │
        └──> Leonmmcoset/MTRPathQQBot  (GPLv3)
                    │
                    └──> 本项目：MTR 寻路 Bot  (GPL-3.0-only)
```

| 上游 | 地址 | 协议 | 本项目对其所做的处理 |
|---|---|---|---|
| mtr-pathfinder | https://github.com/CokeStudios/mtr-pathfinder | GPL-3.0 | 寻路核心（`mtr_pathfinder_v4.py` 的 CSA 寻路、数据抓取、出图渲染）来自该作品；本项目做了兼容性与健壮性修改 |
| MTRPathQQBot | https://github.com/Leonmmcoset/MTRPathQQBot | GPLv3 | 本项目在其基础上继续修改 |

**修改时间**：2026 年 11 月起。
**修改内容**：完整清单见 [项目结构.md](项目结构.md) 的「本次代码修复清单」，摘要如下：

- 修复 Python 3.8 兼容性、子进程编码、`libraqm.dll` 加载等致命问题
- 修正停站时间与站名取值错误（时刻表、运行图）
- 重构命令解析、对外脚本调用与日志机制（新增 `bot_commands.py`、`script_runner.py`、`logging_setup.py`）
- 修复插件层的路径、配置读取与异常处理
- 新增自动化测试 `tests/`（112 项）

本项目**不是**上述任一作品的官方版本，也未获得任何商业背书。

---

## 二、随仓库分发的第三方组件

以下文件物理存在于本仓库中，再分发时必须保留其各自的授权要求。

### 1. Noto Sans 字体族

| 项目 | 内容 |
|---|---|
| 文件 | `botpy/examples/mtr_pathfinder_data/fonts/` 下的 8 个 `.ttf`<br>（NotoSans、NotoSansSC/TC/HK/JP/KR、NotoSansArabic、NotoSansThaiLooped） |
| 协议 | SIL Open Font License 1.1（OFL-1.1） |
| 版权 | Copyright The Noto Project Authors / Google Inc. |
| 再分发要求 | 必须附带 OFL-1.1 协议文本；不得单独售卖字体；如修改字体，衍生字体不得使用保留字体名（Reserved Font Name） |
| 协议全文 | https://openfontlicense.org |

> 这 8 个字体约占仓库 36 MB，用于出图时渲染多语言站名，属于运行时必需资源。

### 2. libraqm

| 项目 | 内容 |
|---|---|
| 文件 | `botpy/examples/libraqm.dll` |
| 协议 | MIT |
| 版权 | Copyright the libraqm contributors |
| 用途 | Pillow 的复杂文本排版（`raqm_support.py` 负责在导入 PIL 前预加载） |

### 3. FriBidi

| 项目 | 内容 |
|---|---|
| 文件 | `botpy/examples/fribidi-0.dll` |
| 协议 | LGPL-2.1-or-later |
| 版权 | Copyright the FriBidi project contributors |
| 用途 | libraqm 的依赖，双向文字（阿拉伯文、希伯来文）排版 |
| 再分发要求 | LGPL 要求随附协议文本，并保证接收方可以替换该库（本项目以独立 DLL 形式提供，可被同名文件替换，满足该要求） |

---

## 三、通过 pip 安装的依赖（不随仓库分发）

以下依赖由使用者在本地通过 `pip install -r requirements.txt` 安装，不包含在本仓库中，
各自遵循其自身协议，详情见对应包的元数据：

`qq-botpy`（MIT）、`opencc`、`pillow`、`fonttools`、`requests`、`aiohttp`、
`sqlalchemy`、`pyyaml`、`selenium`、`networkx`。

其中 `qq-botpy` 是腾讯官方机器人 SDK（MIT），仅作为库被调用，不构成对其代码的修改或再分发。

---

## 四、如有异议

若你是上述任一作品的著作权人，认为本项目的署名、授权或再分发方式存在问题，
请提交 Issue 或直接联系仓库维护者，我们会尽快处理。
