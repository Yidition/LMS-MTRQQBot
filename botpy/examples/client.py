# -*- coding: utf-8 -*- #
import base64
import os
import re
import tempfile
import time

import aiohttp
import botpy
from botpy.ext.cog_yaml import read
from botpy.message import GroupMessage

import bot_commands as cmds
import logging_setup
from script_runner import run_script

# 所有外部脚本都以 examples 目录为工作目录运行：脚本内部大量使用相对路径
# （mtr_pathfinder_data / mtr_pathfinder_temp / chat_bot.db / mtr-*.json），
# cwd 不对就会读不到资源或把缓存写到奇怪的地方。
# All external scripts run with the examples directory as their working directory: they
# use many relative paths (mtr_pathfinder_data / mtr_pathfinder_temp / chat_bot.db /
# mtr-*.json), so a wrong cwd misses resources or writes the cache to odd places.
EXAMPLES_DIR = cmds.EXAMPLES_DIR
CONFIG_PATH = os.path.join(EXAMPLES_DIR, "config.yaml")

#: 与 QQ 开放平台交互的 HTTP 超时，避免网络卡住时整个 handler 挂死
#: HTTP timeout for QQ Open Platform requests, so a stalled network cannot hang the handler.
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60)

# 统一日志：<examples>/logs/bot.log（UTF-8，按大小轮转），同时把 botpy 自己的
# 日志并进同一个文件。日志目录不可写时自动降级为只输出控制台。
# Unified logging: <examples>/logs/bot.log (UTF-8, rotated by size), with botpy's own
# logs merged into the same file. If the log directory is not writable, logging degrades
# to console output only.
_log = logging_setup.setup(merge_botpy=True)


def load_config(path=CONFIG_PATH):
    """读取并校验 config.yaml，缺关键字段时给出可读的报错而不是 KeyError。 / Read and validate config.yaml, raising a readable error instead of KeyError when key fields are missing."""
    if not os.path.isfile(path):
        raise SystemExit(
            "找不到配置文件：%s\n请按 README 填写 appid / secret 后再启动。" % path
        )
    config = read(path) or {}
    missing = [key for key in ("appid", "secret") if not str(config.get(key, "")).strip()]
    if missing:
        raise SystemExit("配置文件 %s 缺少必需字段：%s" % (path, "、".join(missing)))
    return config


test_config = load_config()

if not str(test_config.get("picturesToken", "")).strip():
    _log.warning(
        "config.yaml 未配置 picturesToken，图床相关功能（plugins/img_upload.py）不可用"
    )

# ==========================================
# 核心底层：直接通过 HTTP 请求发送 Base64 图片
# Core internals: send Base64 images directly over HTTP.
# ==========================================
async def send_base64_image(client, group_openid, msg_id, file_path):
    started = time.perf_counter()
    try:
        size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")
        _log.info(
            "准备上传图片 file=%s 原始=%dB base64=%dB",
            os.path.basename(file_path), size, len(base64_data),
        )
        
        access_token = None
        try:
            access_token = client.http.token.access_token
        except AttributeError:
            _log.warning("取不到 client 里的 access_token，改为重新申请")
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                token_url = "https://bots.qq.com/app/getAppAccessToken"
                token_payload = {
                    "appId": test_config["appid"],
                    "clientSecret": test_config["secret"]
                }
                async with session.post(token_url, json=token_payload) as resp:
                    token_res = await resp.json()
                    access_token = token_res.get("access_token")
                    _log.info("重新申请 access_token 完成 status=%s", resp.status)
        
        if not access_token:
            _log.error("无法获取 Access Token")
            return False
            
        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json"
        }
        
        upload_url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/files"
        upload_payload = {
            "file_type": 1,
            "file_data": base64_data
        }
        
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.post(upload_url, headers=headers, json=upload_payload) as resp:
                upload_res = await resp.json()
                _log.info("上传文件返回 status=%s", resp.status)
                _log.debug("上传响应体: %s", upload_res)
                
                file_info = upload_res.get("file_info")
                if not file_info:
                    _log.error(f"上传文件未返回 file_info: {upload_res}")
                    return False
                
            send_url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/messages"
            send_payload = {
                "msg_type": 7,
                "msg_id": msg_id,
                "media": {"file_info": file_info}
            }
            
            async with session.post(send_url, headers=headers, json=send_payload) as resp:
                send_res = await resp.json()
                elapsed = (time.perf_counter() - started) * 1000
                _log.info(
                    "发送图片返回 status=%s 总耗时=%.0fms", resp.status, elapsed
                )
                _log.debug("发送响应体: %s", send_res)
                if resp.status == 200:
                    _log.info("图片发送成功")
                    return True
                _log.error("发送消息失败 status=%s body=%s", resp.status, send_res)
                return False
                    
    except Exception:
        _log.exception("发送图片过程发生异常 file=%s", file_path)
        return False

class MyClient(botpy.Client):
    async def on_ready(self):
        _log.info(f"机器人「{self.robot.name}」启动完成！")

    async def _reply(self, message, content):
        """回复一条文本消息。 / Reply with a text message."""
        await message._api.post_group_message(
            group_openid=message.group_openid,
            msg_type=0,
            msg_id=message.id,
            content=content,
        )

    @staticmethod
    def _output_path(prefix, message_id):
        """给本次请求分配一个临时图片路径。

        写到系统临时目录而不是项目目录：机器人工作目录可能是只读的，
        而且原来的实现会把 png 散落在 examples 下面。

        Allocate a temp image path for this request.

        Write to the system temp directory rather than the project directory: the bot's
        working directory may be read-only, and the old implementation scattered PNGs
        under examples.
        """
        safe = re.sub(r"[^\w\-]", "_", str(message_id))[:64] or "msg"
        return os.path.join(tempfile.gettempdir(), "mtrqqbot_%s_%s.png" % (prefix, safe))

    async def _generate_and_send(self, message, label, script, args, output_path,
                                 timeout=cmds.SCRIPT_TIMEOUT):
        """跑脚本 → 校验产物 → 上传发送，失败时把原因回给用户。 / Run the script, verify the output, then upload and send it; report failures to the user."""
        try:
            result = await run_script(script, *args, timeout=timeout)
            if result is None:
                await self._reply(message, "%s生成超时（超过 %d 秒），请稍后重试。" % (label, timeout))
                return

            ok, detail = cmds.interpret_result(result.stdout, result.stderr, result.returncode)
            if not ok:
                _log.error("%s 生成失败: %s", label, detail)
                await self._reply(message, "%s生成失败：\n%s" % (label, detail))
                return

            if not os.path.isfile(output_path):
                _log.error("%s 报告成功但找不到产物: %s", label, output_path)
                await self._reply(message, "%s生成成功，但没有找到输出文件。" % label)
                return

            _log.info("%s 生成成功，准备上传: %s", label, output_path)
            sent = await send_base64_image(
                client=self,
                group_openid=message.group_openid,
                msg_id=message.id,
                file_path=output_path,
            )
            if not sent:
                await self._reply(message, "%s生成成功，但上传失败。" % label)
        except Exception as exc:  # 兜底，别让单个请求把 handler 打挂 / Fallback: never let one request kill the handler
            _log.exception("%s 处理异常", label)
            await self._reply(message, "系统执行出错：%s" % exc)
        finally:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError as exc:
                _log.warning("清理临时文件失败: %s", exc)

    @logging_setup.traced
    async def on_group_at_message_create(self, message: GroupMessage):
        raw = (message.content or "").strip()
        _log.info("bot 收到消息: %s", raw)

        # 先剥掉 --no-xxx 寻路参数，再识别命令
        # Strip the --no-xxx pathfinding options first, then match the command.
        clean_msg, final_args = cmds.split_no_options(raw)
        command, rest = cmds.match_command(clean_msg)

        # ======= 隐藏指令 1：测试存活 =======
        # ======= Hidden command 1: liveness check =======
        if command == "ping":
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content="Pong! 机器人在线并运行正常。"
            )
            return

        # ======= 隐藏指令 2：彩蛋 =======
        # ======= Hidden command 2: easter egg =======
        elif command == "secret":
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content="你发现了隐藏指令！可惜这里没有宝藏，只有一个无情的 MTR 寻路机器。"
            )
            return

        # ======= 整活指令：/ds-think =======
        # ======= Gag command: /ds-think =======
        elif command == "ds-think":
            think_text = (
                "分析问题所在：\n"
                "这是一个环线（Loop Line）！\n"
                "看名字 YRT Loop Line CW (顺时针)，以及站点顺序：\n"
                "小齐中心 -> 玻璃 -> ... -> LMSC中環 -> (环线特点：首尾相连)\n"
                "环线的特点是第一站和最后一站是同一个站或者相连的，列车会一直转圈。\n"
                "导致运行图出现这种“V”字型或者交叉的原因：\n\n"
                "1. 数据源里 YRT Loop Line CW 的 stations 数组里，记录的并不是一次单程的站点，而是包含了一整圈的站点，甚至可能包含了多圈。\n"
                "2. 环线数据的特点：比如经过 小齐中心 -> ... -> LMSC中環 -> 小齐中心。\n"
                "3. 代码的截断逻辑是：遇到重复站点就截断。所以它截断到了 LMSC中環。但是，对于环线来说，起点和终点是相连的。\n"
                "4. 更奇怪的是：红线折返了（V字底在 LMSC中環，然后反向向上停在了 沙平恶）。这说明：Y轴的站点顺序与列车实际的运行方向反向的部分冲突了。\n\n"
                "核心问题：\n"
                "用户输入的 YRT Loop Line CW 在匹配时，可能同时匹配到了上行的数据，而且它把一整圈的运行轨迹压缩在一张图里了。数据的站序就是：从站0到站15，然后再从站15到站4... 这是一个“折返”或者“部分环线”的数据。\n\n"
                "解决办法：\n"
                "对于环线，最合理的方法是在运行图中，把环线展开，或者只画单圈。"
            )
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=think_text
            )
            return

        # ======= 指令：朋友的酒歌词 =======
        # ======= Command: lyrics of "A Friend's Wine" =======
        elif command == "xjy":
            lyrics = (
                "《朋友的酒》 - 李晓杰\n\n"
                "昨日一去不复回 哦也\n"
                "开心比什么都贵\n"
                "覆水不能再收回 哦也\n"
                "桃花谢了有玫瑰\n"
                "人生几十年 总会有风雨来陪\n"
                "潇潇洒洒 赴会 今不醉不归\n"
                "往事后不后悔 慢慢去体会\n"
                "此刻朋友这杯酒最珍贵\n\n"
                "快把酒满上 干了这杯 大声歌唱\n"
                "好朋友好朋友 今宵多欢畅\n"
                "理想改变了 我们的模样\n"
                "也让我 懂得了要珍惜 朋友的肩膀\n"
                "阳光总会在 风雨之后 撒向苍茫\n"
                "让我们抬起头 学会了坚强\n"
                "就像朋友的 这杯烈酒 烫我心上\n"
                "温暖我 凡事别再放心上"
            )
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=lyrics
            )
            return

        # ======= 指令：/ban 封禁整活 =======
        # ======= Command: /ban ban gag =======
        elif command == "ban":
            ban_text = (
                "JS功能目前处于高度试验性状态，可能包含大量 bug\n"
                "请前往点击这里反馈问题反馈问题\n"
                "[Axiom] Tip : Hocessthefixiomconfigbyrunning / axiomconfig\n"
                "已封禁 xiaoyiyangyang : Banned by an operator .\n"
                "xiaoyiyangyang 退出了游戏\n"
                "没有玩家\n"
                "共有2条载1\n"
                "Help 被 xiaoyiyangyang 封禁◇ Bannedbyanoperator .\n"
                "xiaoyiyangyang 被 qnqe 封禁： Banned by an operator .\n"
                "已解封 xiaoyiyangyang \n"
                "xiaoyiyangyang 加入了游戏\n"
                "已解封 Help \n"
                "光影包已禁用！\n"
                "< xiaoyiyangyang ＞警告一次\n"
                "< qnqe >???\n"
                "< xiaoyiyangyang ＞再来一次永封\n"
                "< qnqe > wc \n"
                "[ xiaoyiyangyang :已将 qnqe 设为服务器管理员1\n"
                "[ Axiom ] Tip : Accessthefixiomconfigby running"
            )
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=ban_text
            )
            return

        # ======= 指令：/jam 堵车整活 =======
        # ======= Command: /jam traffic-jam gag =======
        elif command == "jam":
            jam_text = (
                "怎么DTMR又堵车了？！\n"
                "《面面相觑》\n"
                "《互通线》"
            )
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content=jam_text
            )
            return

        # ======= 指令：/lps 找人 =======
        # ======= Command: /lps looking for players =======
        elif command == "lps":
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                content="有人上官服吗？"
            )
            return

        # ======= 指令：/时刻表 线路名 =======
        # ======= Command: /timetable <route name> =======
        elif command == "timetable":
            route_name = rest
            if not route_name:
                await self._reply(message, "用法：/时刻表 [线路名]\n例如：/时刻表 互通线")
                return

            _log.info("开始生成时刻表: %s", route_name)
            output_path = self._output_path("timetable", message.id)
            await self._generate_and_send(
                message, "时刻表", "mtr_timetable.py",
                [route_name, "--output", output_path],
                output_path,
            )
            return

        # ======= 指令：/运行图 线路名 =======
        # ======= Command: /diagram <route name> =======
        elif command == "diagram":
            route_name = rest
            if not route_name:
                await self._reply(message, "用法：/运行图 [线路名]\n例如：/运行图 互通线")
                return

            _log.info("开始生成运行图: %s", route_name)
            output_path = self._output_path("diagram", message.id)
            await self._generate_and_send(
                message, "运行图", "mtr_diagram.py",
                [route_name, "--output", output_path, "--max-trains", "10"],
                output_path,
            )
            return

        # ======= 正常寻路指令 (/go 或 /路线) =======
        # ======= Normal pathfinding command (/go or /路线) =======
        elif command == "route":
            input_content = rest
            
            if not input_content:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=0,
                    msg_id=message.id,
                    content="格式：/go 或 /路线 [起点];[终点] [可选参数]\n可选参数：--no-highspeed, --no-lightrail, --no-[线路名]"
                )
                return

            semicolon_index = input_content.find(';')
            
            if semicolon_index != -1:
                starta = input_content[:semicolon_index].strip()
                enda = input_content[semicolon_index + 1:].strip()
                
                if not starta or not enda:
                    await message._api.post_group_message(
                        group_openid=message.group_openid,
                        msg_type=0,
                        msg_id=message.id,
                        content="起点或终点不能为空！"
                    )
                    return
                    
                if starta == enda:
                    await message._api.post_group_message(
                        group_openid=message.group_openid,
                        msg_type=0,
                        msg_id=message.id,
                        content="起始站和终点站不能相同！"
                    )
                    return

                _log.info(f'开始处理导航: {starta} -> {enda}, 参数: {final_args}')
                
                output_path = self._output_path("route", message.id)
                
                try:
                    _log.info(f'正在执行寻路脚本...')
                    result = await run_script(
                        'mtr_pathfinder_v4.py', starta, enda,
                        '--output', output_path, *final_args
                    )
                    if result is None:
                        await self._reply(message, '寻路超时（超过 %d 秒），请稍后重试。' % cmds.SCRIPT_TIMEOUT)
                        return
                    
                    if "SUCCESS" in result.stdout:
                        _log.info('寻路成功，准备发送本地图片...')
                        success = await send_base64_image(
                            client=self, 
                            group_openid=message.group_openid, 
                            msg_id=message.id, 
                            file_path=output_path
                        )
                        if not success:
                            await message._api.post_group_message(
                                group_openid=message.group_openid,
                                msg_type=0,
                                msg_id=message.id,
                                content="图片生成成功，但上传失败。请查看后台日志。"
                            )
                    else:
                        _log.error(f"脚本执行失败，输出: {result.stdout}")
                        _log.error(f"错误信息: {result.stderr}")
                        error_msg = result.stderr.strip()[-100:] if result.stderr.strip() else result.stdout.strip()[-100:]
                        
                        await message._api.post_group_message(
                            group_openid=message.group_openid,
                            msg_type=0,
                            msg_id=message.id,
                            content=f"寻路失败，可能是站点名称不正确。\n详情：{error_msg}"
                        )
                except Exception as e:
                    _log.error(f"执行脚本异常: {e}")
                    await message._api.post_group_message(
                        group_openid=message.group_openid,
                        msg_type=0,
                        msg_id=message.id,
                        content=f"系统执行出错：{e}"
                    )
                finally:
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                            _log.info(f"已清理本地临时文件")
                        except Exception as e:
                            _log.warning(f"清理文件失败: {e}")
            else:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=0,
                    msg_id=message.id,
                    content="格式不正确，请使用英文分号';'分隔起点和终点。\n例如：/go Badland;Glass --no-highspeed"
                )

if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True)
    client = MyClient(intents=intents, is_sandbox=False)
    client.run(appid=test_config["appid"], secret=test_config["secret"])
