# LMS-MTRQQBot

一个基于 QQ 官方机器人 API 的 Minecraft Transit Railway 寻路 / 出图机器人：
在群里 @ 机器人发送指令，它会算出两站之间的最优路线、生成时刻表或列车运行图，并把图片发回群里。

- 寻路核心：[CokeStudios/mtr-pathfinder](https://github.com/CokeStudios/mtr-pathfinder)（已针对本项目改造）
- 机器人框架：[tencent-connect/botpy](https://github.com/tencent-connect/botpy)
- 开源协议：[GPL-3.0-only](LICENSE)（详见 [来源与授权](#来源与授权)）

---

## 功能

在群里 **@机器人** 后发送指令（命令前缀 `/`，中文指令同样需要 @）：

| 指令 | 作用 | 示例 |
|---|---|---|
| `/go` `/路线` | 两站之间寻路并返回图片 | `/go 北海洋;恶地` |
| `/时刻表` | 生成指定线路的时刻表 | `/时刻表 7号线` |
| `/运行图` | 生成指定线路的列车运行图 | `/运行图 7号线` |
| `/ping` | 探活 | `/ping` |
| `/secret` `/ds-think` `/xjy` `/ban` `/jam` `/lps` | 整活指令，返回固定文案 | `/jam` |

### 寻路指令格式

```
/go 起点;终点 [可选参数]
/路线 起点;终点 [可选参数]
```

- 起点和终点**必须用英文分号 `;` 分隔**（中文分号不行）
- 起点终点不能为空，也不能相同
- 站名支持中文名、英文名或完整名（如 `北海洋`、`North Sea`、`北海洋|North Sea`），
  并会自动做简繁转换；完全匹配不上时还会做相似度匹配（可能匹配到近似站名，注意看生成的图）

可选参数（可组合）：

| 参数 | 含义 |
|---|---|
| `--no-highspeed` | 不坐高铁 |
| `--no-lightrail` | 不坐轻轨 |
| `--no-<线路名>` | 不坐指定线路，如 `--no-7号线` |

例：

```
/go 北海洋;恶地 --no-highspeed
/go 小齐中心;沙平恶 --no-逸扬环线 --no-lightrail
```

---

## 环境要求

- **Windows**（脚本大量使用 Windows 路径与随附的 `libraqm.dll` / `fribidi-0.dll`，目前只在 Windows 上验证过）
- **Python 3.8 及以上**（源码用 `from __future__ import annotations` 兼容 3.8 的内置泛型注解，3.7 及更早不行）
- 需要 `qq-botpy` 和一组图像处理依赖，见 `requirements.txt`

```powershell
pip install -r requirements.txt
```

> 注意：`requirements.txt` 里的 `opencc` 是寻路与出图的必需依赖，缺了会直接 ImportError。

---

## 快速开始

### 1. 准备机器人凭据

从 [QQ 开放平台](https://q.qq.com/) 创建机器人，拿到 **AppID** 和 **AppSecret**。

### 2. 填写配置

编辑 `botpy/examples/config.yaml`：

```yaml
# 必填
appid: "你的 AppID"
secret: "你的 AppSecret"

# 可选：仅当你要使用 plugins/img_upload.py 的 sm.ms 图床功能时才需要
# 不填不影响寻路、时刻表、运行图这些功能
picturesToken: "你的 sm.ms Token"
```

- `appid` / `secret` 缺任意一项，程序启动时就会直接报错退出并说明缺什么。
- 这个文件含密钥，已被 `.gitignore` 排除，所以**克隆下来可能没有它**——没有就新建一个，内容照上面写。
- 也不要用 `git add -f` 硬提交，泄露了要去开放平台重置。

### 3. 准备数据源

寻路需要一份 MTR 地图线路数据。代码里把数据源写死为：

```python
LINK = 'http://localhost:1025'
```

启动后会请求该地址的 `/mtr/api/map/stations-and-routes` 和 `/mtr/api/map/departures`。
**所以本机需要跑着这样一个 MTR 地图服务，否则寻路会失败**（时刻表 / 运行图读的是本地缓存，不依赖它）。

数据抓到后会缓存在 `botpy/examples/` 下：

```
mtr-original-data-<hash>-mtr4-v4.json    线路与站点
mtr-route-departure-<hash>-mtr4-v4.json  发车时刻
```

### 4. 启动

```powershell
cd botpy\examples
python client.py
```

必须在 `botpy/examples` 目录下启动：脚本内部用大量相对路径读写资源与缓存。

---

## 日志与排障

所有日志（本程序 + botpy 内部）统一写到：

```
botpy/examples/logs/bot.log
```

UTF-8，默认单文件 5 MB、保留 5 份轮转备份。每条日志带请求 id（QQ 消息 id 后 8 位），
一次指令的"收消息 → 跑脚本 → 上传 → 结束"可以用同一个 id 串起来：

```powershell
Select-String -Path botpy\examples\logs\bot.log -Pattern 'a1b2c3d4'
```

排障时提高日志级别：

```powershell
$env:MTR_LOG_LEVEL='DEBUG'     # 脚本完整输出、HTTP 响应体、异常堆栈都写进日志
$env:MTR_LOG_CONSOLE='INFO'    # 同时让出图脚本把诊断信息打到控制台
cd botpy\examples
python client.py
```

可配置的环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MTR_LOG_DIR` | `botpy/examples/logs` | 日志目录 |
| `MTR_LOG_LEVEL` | `INFO` | 写文件的级别 |
| `MTR_LOG_CONSOLE` | `WARNING` | 控制台级别（默认低是为了不污染脚本的 stderr，client 靠它判断失败） |
| `MTR_LOG_MAX_BYTES` | `5242880` | 单文件上限 |
| `MTR_LOG_BACKUPS` | `5` | 轮转备份份数 |
| `MTR_PYTHON` | 当前解释器 | 指定跑出图脚本用的 Python |

---

## 测试

在仓库根目录（本 README 所在目录）执行：

```powershell
python -B tests\run_all.py
```

96 项测试，约 3 秒跑完，只用标准库 `unittest`，不需要 pytest。覆盖：

- 命令解析（含 `/google` 不该被当成 `/go` 的回归测试）、参数剥离、起点终点校验
- 停站时间 / 到发偏移 / 颜色解析等数据逻辑
- **真的调用**三个出图脚本，断言退出码、`SUCCESS` 输出和产物是合法 PNG
- 日志：落盘编码、轮转、级别、请求 id、目录不可写时的降级
- 插件：待办增删改查、图床缺 token 的报错、天气格式化容错

测试会自己建临时工作目录并在结束后清理，不会污染项目。

---

## 项目结构

```
MTRPathQQBot-main/
├─ README.md                 本文件
├─ LICENSE                   GPL-3.0-only 协议全文
├─ THIRD-PARTY-NOTICES.md    上游来源、修改声明、第三方组件协议
├─ 项目结构.md               目录职责、路径依赖、修复记录、已知问题（建议一并看）
├─ requirements.txt
├─ tests/                    自动化测试
└─ botpy/examples/           ★ 工作目录
   ├─ client.py             主入口：QQ 群消息与指令分发
   ├─ config.yaml           密钥配置（已 gitignore）
   ├─ mtr_pathfinder_v4.py  寻路核心（当前使用）
   ├─ mtr_timetable.py      时刻表生成（也可单独 CLI 运行）
   ├─ mtr_diagram.py        运行图生成（也可单独 CLI 运行）
   ├─ mtrpath.py            旧版寻路，保留备用
   ├─ mtrpath_beta.py       中间版本，保留备用
   ├─ bot_commands.py       命令解析等纯逻辑
   ├─ script_runner.py      跑外部脚本并记录耗时/返回码
   ├─ logging_setup.py      统一日志
   ├─ raqm_support.py       注册随附的 libraqm.dll
   ├─ mtr_data.py           停站时间等共用数据逻辑
   ├─ plugins/              图床 / 天气 / 运势 / 待办 / 截图（库，未被 client 调用）
   ├─ mtr_pathfinder_data/  图标与字体（约 36 MB）
   └─ logs/                 运行日志
```

细节（路径依赖、修复清单、限制）见 [项目结构.md](项目结构.md)。

---

## 单独运行出图脚本

不需要启动机器人也能出图，方便调试：

```powershell
cd botpy\examples

# 寻路（--no-update 表示只用本地缓存，不联网抓数据）
python mtr_pathfinder_v4.py 北海洋 恶地 --no-update --output C:\tmp\route.png

# 时刻表（读缓存，不需要地图服务）
python mtr_timetable.py "7号线" --output C:\tmp\tt.png

# 运行图
python mtr_diagram.py "7号线" --output C:\tmp\dg.png --max-trains 10
```

成功时 stdout 打印 `SUCCESS:<路径>`，失败时打印 `FAILED` 并返回非 0 退出码。

---

## 常见问题

**寻路一直失败 / 提示"站点名称不正确"**
先看日志。多数是数据源没起（`http://localhost:1025` 访问不通），或站名不在线路数据里。
站名匹配带模糊回退，可能匹配到近似站名，出图后先确认首末站对不对。

**`/时刻表` `/运行图` 提示找不到缓存数据**
这两个指令读的是本地缓存文件，需要先有过一次成功的数据抓取（正常跑一次 `/go` 即可），
或者手动跑一次 `python mtr_pathfinder_v4.py 起点 终点` 让它生成缓存。

**生成成功但上传失败**
图片已经生成，卡在 QQ 的图片上传接口。看日志里 `上传文件返回` / `发送图片返回` 的 status，
常见是 access_token 过期或群 openid 不对。

**`picturesToken` 不填会怎样**
不影响寻路、时刻表、运行图。只有调用 `plugins/img_upload.py`（sm.ms 图床）时才需要，
启动时会打一条 warning 提醒。

**换台机器跑报 `not supported without libraqm`**
说明 Pillow 没找到随项目携带的 `libraqm.dll`。项目里已用 `raqm_support.py` 在导入 PIL 前预加载，
如果仍报错，检查这两个 DLL 是否还在 `botpy/examples/` 下、以及位数是否和 Python 一致（都是 64 位）。

**机器人不响应 @**
确认机器人已加入群、有群消息权限；日志里没有 `收到消息` 说明事件根本没到，
属于开放平台侧的权限/事件订阅问题。

**项目占了 40 MB**
其中约 36 MB 是 `mtr_pathfinder_data/fonts/` 下的 8 套 Noto 字体，出图渲染多语言站名要用，不能删。

---

## 已知限制

- 图床删图走 selenium 打开网页，慢且容易失败（上游实现如此，见 `plugins/img_upload.py`）。
- `plugins/` 下的图床 / 天气 / 运势 / 待办 / 截图目前是**可用的库**，但 `client.py` 没有调用它们，
  要用需要自己接到指令里。
- 寻路依赖本地 MTR 地图服务；离线时只能用已有缓存（`--no-update`）。
- 旧版 `mtrpath.py` / `mtrpath_beta.py` 只做兼容性修复，实际使用的是 `mtr_pathfinder_v4.py`。

---

## 来源与授权

本项目的衍生链：

```
CokeStudios/mtr-pathfinder  (GPL-3.0)
        │
        └──> Leonmmcoset/MTRPathQQBot  (GPLv3)
                    │
                    └──> 本项目  (GPL-3.0-only)
```

| 上游 | 说明 | 协议 |
|---|---|---|
| [CokeStudios/mtr-pathfinder](https://github.com/CokeStudios/mtr-pathfinder) | 寻路算法与出图渲染的来源 | GPL-3.0 |
| [Leonmmcoset/MTRPathQQBot](https://github.com/Leonmmcoset/MTRPathQQBot) | 本项目的直接上游 | GPLv3 |
| [tencent-connect/botpy](https://github.com/tencent-connect/botpy) | 机器人框架（作为依赖库使用） | MIT |

### 协议

本项目整体以 **GPL-3.0-only** 授权，协议全文见 [LICENSE](LICENSE)。

```text
SPDX-License-Identifier: GPL-3.0-only
```

之所以是 GPLv3 而不是 MIT/Apache：本项目是上述 GPL 作品的衍生作品，
分发时**必须**继续以 GPLv3 授权，这是上游协议的要求，而非可选项。
除非同时取得两位上游作者的授权，否则不能改为更宽松的协议。

依据 GPLv3 第 5(a) 条，这里明确声明：**本项目修改过上游作品**，
修改时间为 2026 年 11 月起，修改内容见 [项目结构.md](项目结构.md) 的「本次代码修复清单」。

### 第三方组件

仓库内随附了字体与 DLL，再分发时需遵守各自的协议（Noto 字体为 OFL-1.1、
`libraqm.dll` 为 MIT、`fribidi-0.dll` 为 LGPL-2.1+）。
完整清单与再分发要求见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

---

遇到问题请提交 Issue，并附上 `logs/bot.log` 里对应请求 id 的日志。
