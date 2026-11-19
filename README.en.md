# MTR Pathfinding Bot

> [中文](README.md) · English

A Minecraft Transit Railway pathfinding / image-rendering bot built on the official QQ bot API:
@ the bot in a group with a command, and it computes the optimal route between two stations,
generates a timetable or a train diagram, and sends the image back to the group.

- Pathfinding core: [CokeStudios/mtr-pathfinder](https://github.com/CokeStudios/mtr-pathfinder) (modified for this project)
- Bot framework: [tencent-connect/botpy](https://github.com/tencent-connect/botpy)
- License: [GPL-3.0-only](LICENSE) (see [Origin and Licensing](#origin-and-licensing))

---

## Features

In a group, **@ the bot** and then send a command (command prefix `/`; Chinese commands likewise require the @):

| Command | Purpose | Example |
|---|---|---|
| `/go` `/路线` | Pathfind between two stations and return an image | `/go 北海洋;恶地` |
| `/时刻表` | Generate the timetable for the specified route | `/时刻表 7号线` |
| `/运行图` | Generate the train diagram for the specified route | `/运行图 7号线` |
| `/ping` | Liveness check | `/ping` |
| `/secret` `/ds-think` `/xjy` `/ban` `/jam` `/lps` | Fun commands that return fixed text | `/jam` |

### Pathfinding Command Format

```
/go 起点;终点 [可选参数]
/路线 起点;终点 [可选参数]
```

- Start and end **must be separated by an ASCII semicolon `;`** (the Chinese semicolon does not work)
- Start and end must not be empty, and must not be the same
- Station names accept Chinese names, English names, or full names (e.g. `北海洋`, `North Sea`, `北海洋|North Sea`),
  and are converted between Simplified and Traditional Chinese automatically; when there is no exact match,
  similarity matching is also performed (it may match a similar station name, so check the generated image)

Optional parameters (combinable):

| Parameter | Meaning |
|---|---|
| `--no-highspeed` | Do not take high-speed rail |
| `--no-lightrail` | Do not take light rail |
| `--no-<线路名>` | Do not take the specified route, e.g. `--no-7号线` |

Example:

```
/go 北海洋;恶地 --no-highspeed
/go 小齐中心;沙平恶 --no-逸扬环线 --no-lightrail
```

---

## Environment Requirements

- **Windows** (the scripts make heavy use of Windows paths and the bundled `libraqm.dll` / `fribidi-0.dll`; so far verified only on Windows)
- **Python 3.8 or later** (the source uses `from __future__ import annotations` for compatibility with 3.8's built-in generic annotations; 3.7 and earlier do not work)
- Requires `qq-botpy` and a set of image-processing dependencies, see `requirements.txt`

```powershell
pip install -r requirements.txt
```

> Note: `opencc` in `requirements.txt` is a required dependency for pathfinding and rendering; without it you get an ImportError immediately.

---

## Quick Start

### 1. Prepare Bot Credentials

Create a bot on the [QQ Open Platform](https://q.qq.com/) and obtain the **AppID** and **AppSecret**.

### 2. Fill In the Configuration

Edit `botpy/examples/config.yaml`:

```yaml
# 必填
appid: "你的 AppID"
secret: "你的 AppSecret"

# 可选：仅当你要使用 plugins/img_upload.py 的 sm.ms 图床功能时才需要
# 不填不影响寻路、时刻表、运行图这些功能
picturesToken: "你的 sm.ms Token"
```

- If either `appid` / `secret` is missing, the program reports an error and exits immediately at startup, stating what is missing.
- This file contains secrets and is already excluded by `.gitignore`, so **a fresh clone may not contain it** — if it is missing, create one with the content shown above.
- Do not force-commit it with `git add -f` either; if it leaks, reset it on the Open Platform.

### 3. Prepare the Data Source

Pathfinding needs a copy of the MTR map route data. The data source is hard-coded in the code as:

```python
LINK = 'http://localhost:1025'
```

After startup it requests `/mtr/api/map/stations-and-routes` and `/mtr/api/map/departures` from that address.
When the service is unavailable, the program **automatically falls back to the local cache** and keeps working (it writes one log entry and shows the prompt "改用本地缓存" on the console);
it only truly fails when the cache is also missing.

Once the data has been fetched it is cached under `botpy/examples/`:

```
mtr-original-data-<hash>-mtr4-v4.json    线路与站点
mtr-route-departure-<hash>-mtr4-v4.json  发车时刻
```

### 4. Start

```powershell
cd botpy\examples
python client.py
```

You must start it from the `botpy/examples` directory: internally the scripts use a large number of relative paths to read and write resources and caches.

---

## Logs and Troubleshooting

All logs (this program + botpy internals) are written uniformly to:

```
botpy/examples/logs/bot.log
```

UTF-8, default single file 5 MB, keeping 5 rotation backups. Every log line carries a request id (the last 8 digits of the QQ message id),
so one command's "receive message → run script → upload → finish" can be threaded together with the same id:

```powershell
Select-String -Path botpy\examples\logs\bot.log -Pattern 'a1b2c3d4'
```

Raise the log level when troubleshooting:

```powershell
$env:MTR_LOG_LEVEL='DEBUG'     # 脚本完整输出、HTTP 响应体、异常堆栈都写进日志
$env:MTR_LOG_CONSOLE='INFO'    # 同时让出图脚本把诊断信息打到控制台
cd botpy\examples
python client.py
```

Configurable environment variables:

| Variable | Default | Description |
|---|---|---|
| `MTR_LOG_DIR` | `botpy/examples/logs` | Log directory |
| `MTR_LOG_LEVEL` | `INFO` | Level written to the file |
| `MTR_LOG_CONSOLE` | `WARNING` | Console level (default is low so as not to pollute the script's stderr, which the client uses to judge failure) |
| `MTR_LOG_MAX_BYTES` | `5242880` | Maximum size per file |
| `MTR_LOG_BACKUPS` | `5` | Number of rotation backups |
| `MTR_PYTHON` | Current interpreter | Python used to run the rendering scripts |

---

## Tests

Run from the repository root (the directory containing this README):

```powershell
python -B tests\run_all.py
```

112 tests, finishing in about 30 seconds, using only the standard library `unittest`, no pytest needed. Coverage:

- Command parsing (including the regression test that `/google` must not be treated as `/go`), parameter stripping, start/end validation
- Data logic such as dwell time / arrival-departure offsets / color parsing
- **Really invokes** the three rendering scripts, asserting the exit code, the `SUCCESS` output, and that the artifact is a valid PNG
- **Really runs client.py** (with botpy/aiohttp stand-ins): text commands, parameter pass-through, the full `/时刻表` chain of rendering and uploading, the upload-failure branch
- Logging: on-disk encoding, rotation, levels, request id, degradation when the directory is not writable
- Plugins: to-do add/delete/update/query, the error when the image host token is missing, weather formatting fault tolerance

The tests create their own temporary working directory and clean it up afterwards, so they do not pollute the project.

---

## Project Structure

```
MTRPathQQBot-main/
├─ README.md                 Chinese README
├─ README.en.md              English README (this file)
├─ LICENSE                   Full text of GPL-3.0-only
├─ THIRD-PARTY-NOTICES.md    Upstream sources, modification notice, third-party components
├─ THIRD-PARTY-NOTICES.en.md Same, in English
├─ 项目结构.md               Layout, path dependencies, fix log, known issues
├─ 项目结构.en.md            Same, in English
├─ requirements.txt
├─ tests/                    Automated tests
└─ botpy/examples/           ★ Working directory
   ├─ client.py             Entry point: QQ group messages and command dispatch
   ├─ config.yaml           Credentials (gitignored)
   ├─ mtr_pathfinder_v4.py  Pathfinding core (in use)
   ├─ mtr_timetable.py      Timetable generator (also a standalone CLI)
   ├─ mtr_diagram.py        Train diagram generator (also a standalone CLI)
   ├─ bot_commands.py       Pure helpers: command parsing
   ├─ script_runner.py      Runs external scripts, logs duration and exit code
   ├─ logging_setup.py      Unified logging
   ├─ raqm_support.py       Registers the bundled libraqm.dll
   ├─ mtr_data.py           Shared data logic: dwell time and offsets
   ├─ plugins/              Image host / weather / fortune / to-do / screenshot (libraries, not called by client)
   ├─ mtr_pathfinder_data/  Icons and fonts (~36 MB)
   └─ logs/                 Runtime logs
```

For details (path dependencies, fix list, limitations) see [项目结构.en.md](项目结构.en.md).

---

## Running the Rendering Scripts Standalone

You can render images without starting the bot, which is convenient for debugging:

```powershell
cd botpy\examples

# 寻路（--no-update 表示只用本地缓存，不联网抓数据）
python mtr_pathfinder_v4.py 北海洋 恶地 --no-update --output C:\tmp\route.png

# 时刻表（读缓存，不需要地图服务）
python mtr_timetable.py "7号线" --output C:\tmp\tt.png

# 运行图
python mtr_diagram.py "7号线" --output C:\tmp\dg.png --max-trains 10
```

On success, stdout prints `SUCCESS:<路径>`; on failure it prints `FAILED` and returns a non-zero exit code.

---

## FAQ

**Pathfinding keeps failing / reports "站点名称不正确" (station name incorrect)**
Check the logs first. When the map service is unavailable the program falls back to the cache automatically, so the more common cause now is that the station name is not in the route data,
or that there is not even a local cache (the log will contain the two entries "拉取地图数据失败" and "改用本地缓存").
Station name matching has a fuzzy fallback and may match a similar station name, so confirm that the first and last stations are correct after the image is generated.

**`/时刻表` `/运行图` report that no cached data can be found**
These two commands read local cache files, so a successful data fetch must have happened before (normally just running `/go` once),
or manually run `python mtr_pathfinder_v4.py 起点 终点` once to generate the cache.

**Generation succeeds but upload fails**
The image has been generated; it is stuck at QQ's image upload API. Look at the status of `上传文件返回` / `发送图片返回` in the log;
the common causes are an expired access_token or a wrong group openid.

**What happens if `picturesToken` is not filled in**
It does not affect pathfinding, timetables, or train diagrams. It is only needed when calling `plugins/img_upload.py` (the sm.ms image host),
and a warning is printed at startup as a reminder.

**Running it on another machine reports `not supported without libraqm`**
This means Pillow did not find the `libraqm.dll` shipped with the project. The project already uses `raqm_support.py` to preload it before importing PIL;
if the error persists, check whether these two DLLs are still under `botpy/examples/`, and whether their bitness matches Python (both 64-bit).

**The bot does not respond to @**
Confirm that the bot has joined the group and has group message permission; if the log contains no `收到消息`, the event never arrived at all,
which is a permission / event-subscription problem on the Open Platform side.

**The project takes up 40 MB**
About 36 MB of that is the 8 Noto font families under `mtr_pathfinder_data/fonts/`, which are needed to render multilingual station names in images and must not be deleted.

---

## Known Limitations

- Deleting an image from the image host opens a web page through selenium, which is slow and prone to failure (inherited from the upstream implementation, see `plugins/img_upload.py`).
- The image host / weather / fortune / to-do / screenshot modules under `plugins/` are currently **usable libraries**, but `client.py` does not call them;
  to use them you need to wire them into commands yourself.
- Pathfinding prefers online data and falls back to the local cache automatically when the map service is unavailable; it only fails when neither is available.

---

## Origin and Licensing

The derivation chain of this project:

```
CokeStudios/mtr-pathfinder  (GPL-3.0)
        │
        └──> Leonmmcoset/MTRPathQQBot  (GPLv3)
                    │
                    └──> 本项目  (GPL-3.0-only)
```

| Upstream | Description | License |
|---|---|---|
| [CokeStudios/mtr-pathfinder](https://github.com/CokeStudios/mtr-pathfinder) | Source of the pathfinding algorithm and image rendering | GPL-3.0 |
| [Leonmmcoset/MTRPathQQBot](https://github.com/Leonmmcoset/MTRPathQQBot) | The direct upstream of this project | GPLv3 |
| [tencent-connect/botpy](https://github.com/tencent-connect/botpy) | Bot framework (used as a dependency library) | MIT |

### License

This project as a whole is licensed under **GPL-3.0-only**; the full license text is in [LICENSE](LICENSE).

```text
SPDX-License-Identifier: GPL-3.0-only
```

The reason it is GPLv3 rather than MIT/Apache: this project is a derivative work of the GPL works mentioned above,
and distribution **must** continue under GPLv3 — this is a requirement of the upstream licenses, not an option.
Unless permission is obtained from both upstream authors at the same time, it cannot be relicensed under a more permissive license.

Pursuant to GPLv3 Section 5(a), it is explicitly declared here that **this project has modified the upstream works**,
with modifications beginning in November 2026; for the content of the modifications see the "This Round's Code Fix List" in [项目结构.en.md](项目结构.en.md).

### Third-Party Components

The repository bundles fonts and DLLs, and redistribution must comply with their respective licenses (the Noto fonts are OFL-1.1,
`libraqm.dll` is MIT, `fribidi-0.dll` is LGPL-2.1+).
For the complete list and redistribution requirements see [THIRD-PARTY-NOTICES.en.md](THIRD-PARTY-NOTICES.en.md).

---

If you run into problems, please file an Issue and attach the log lines for the corresponding request id from `logs/bot.log`.
