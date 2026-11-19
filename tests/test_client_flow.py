# -*- coding: utf-8 -*-
"""client.py 的功能测试：用替身模块把机器人真正跑起来。

本机没有 `qq-botpy` 和 `aiohttp`，所以这里造最小替身——
只实现 client.py 实际用到的那几个接口，让消息处理全链路可执行：

    收到消息 → 命令解析 → 跑真子进程 → 调上传接口（假）→ 回复

`/时刻表` 会**真的生成 PNG** 并进入上传流程（上传被替换成记录调用）。
`/go` 依赖 `http://localhost:1025` 的地图数据源，本环境没有，
所以走的是失败分支；`/go` 的成功出图由 test_render 用 `--no-update` 覆盖。

Functional tests for client.py: run the bot for real against stub modules.

qq-botpy and aiohttp are not installed here, so minimal stubs are built that
implement only the interfaces client.py actually uses, making the whole message
pipeline executable:

    receive message → parse command → run a real subprocess → call the upload
    interface (fake upload) → reply

`/时刻表` **really generates a PNG** and enters the upload flow (the upload is
replaced by a call recorder). `/go` depends on the map data source at
`http://localhost:1025`, which is absent here, so it takes the failure branch;
successful `/go` rendering is covered by test_render with `--no-update`.
"""

import asyncio
import glob
import os
import shutil
import sys
import tempfile
import types
import unittest

import support

support.ensure_examples_on_path()

#: 记录所有 HTTP 请求，供断言使用
#: Records every HTTP request for assertions.
HTTP_REQUESTS = []


def _install_stubs():
    """在 import client 之前装好 botpy / aiohttp 替身。 / Install the botpy / aiohttp stubs before client is imported."""
    import yaml

    # ---------- botpy ----------
    botpy = types.ModuleType("botpy")

    class Client:
        def __init__(self, intents=None, is_sandbox=False):
            self.intents = intents
            self.is_sandbox = is_sandbox
            self.http = types.SimpleNamespace(
                token=types.SimpleNamespace(access_token="FAKE_TOKEN")
            )

        def run(self, *args, **kwargs):
            raise AssertionError("测试里不应真正启动机器人")

    class Intents:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    botpy.Client = Client
    botpy.Intents = Intents

    ext = types.ModuleType("botpy.ext")
    cog_yaml = types.ModuleType("botpy.ext.cog_yaml")
    cog_yaml.read = lambda path: yaml.safe_load(open(path, encoding="utf-8"))
    ext.cog_yaml = cog_yaml
    botpy.ext = ext

    message_mod = types.ModuleType("botpy.message")

    class GroupMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    message_mod.GroupMessage = GroupMessage
    botpy.message = message_mod

    sys.modules["botpy"] = botpy
    sys.modules["botpy.ext"] = ext
    sys.modules["botpy.ext.cog_yaml"] = cog_yaml
    sys.modules["botpy.message"] = message_mod

    # ---------- aiohttp ----------
    aiohttp = types.ModuleType("aiohttp")

    class ClientTimeout:
        def __init__(self, total=None):
            self.total = total

    class _Resp:
        def __init__(self, status, payload):
            self.status = status
            self._payload = payload

        async def json(self):
            return self._payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class ClientSession:
        #: 按顺序消费的 (status, payload) 队列
        #: Queue of (status, payload) pairs consumed in order.
        responses = []

        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            HTTP_REQUESTS.append({"url": url, **kwargs})
            if ClientSession.responses:
                status, payload = ClientSession.responses.pop(0)
            else:
                status, payload = 200, {}
            return _Resp(status, payload)

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientSession = ClientSession
    sys.modules["aiohttp"] = aiohttp

    return ClientSession


class _FakeApi:
    def __init__(self):
        self.calls = []

    async def post_group_message(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "reply"}


def _make_message(content, msg_id="MSGID00000000A1"):
    message = types.SimpleNamespace()
    message.content = content
    message.id = msg_id
    message.group_openid = "GROUP_OPENID"
    message.author = types.SimpleNamespace(member_openid="USER_OPENID")
    message._api = _FakeApi()
    return message


class ClientFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mtr-client-")
        os.environ["MTR_LOG_DIR"] = cls.tmp

        cls.session_cls = _install_stubs()

        cls.work = support.workspace()
        for path in glob.glob(os.path.join(support.EXAMPLES_DIR, "*.py")):
            shutil.copy2(path, cls.work)

        import bot_commands as cmds
        cls.cmds = cmds
        cls.real_examples_dir = cmds.EXAMPLES_DIR

        # 必须先 import client：它在模块导入时就会读 config.yaml，
        # 而临时工作区里没有配置文件。改 EXAMPLES_DIR 只影响子进程的 cwd 与脚本路径，
        # 那是在调用时读取的，所以放在 import 之后。
        # client must be imported first: it reads config.yaml at module import
        # time, and the temporary workspace has no config file. Changing
        # EXAMPLES_DIR only affects the subprocess cwd and script paths, which
        # are read at call time, so it happens after the import.
        import client
        cls.client_module = client
        cls.bot = client.MyClient(intents=None)

        cmds.EXAMPLES_DIR = cls.work

    @classmethod
    def tearDownClass(cls):
        cls.cmds.EXAMPLES_DIR = cls.real_examples_dir
        # client.py 导入时配置过日志，文件处理器还占着 <tmp>/bot.log；
        # Windows 上不先释放，rmtree 会静默失败，每跑一次泄漏一个临时目录
        # client.py configures logging on import, and its file handler still
        # holds <tmp>/bot.log; on Windows rmtree fails silently unless the file
        # is released first, leaking one temporary directory per run.
        import logging_setup
        logging_setup.setup_console()
        os.environ.pop("MTR_LOG_DIR", None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        HTTP_REQUESTS.clear()
        self.session_cls.responses = []
        # 上传成功 + 发送成功
        # Upload succeeds and sending succeeds.
        self.session_cls.responses = [
            (200, {"file_info": "FILEINFO"}),
            (200, {"id": "sent"}),
        ]

    def run_command(self, content, msg_id="MSGID00000000A1"):
        message = _make_message(content, msg_id)
        asyncio.run(self.bot.on_group_at_message_create(message))
        return message._api.calls

    # ---------- 文本指令 ----------
    # ---------- Text commands ----------

    def test_ping(self):
        replies = self.run_command("/ping")
        self.assertEqual(len(replies), 1)
        self.assertIn("Pong", replies[0]["content"])

    def test_jam_easter_egg(self):
        replies = self.run_command("/jam")
        self.assertIn("DTMR", replies[0]["content"])

    def test_unknown_command_is_silent(self):
        # /google 不应该被当成 /go，也不能乱回复
        # /google must not be treated as /go, and no stray reply may be sent.
        self.assertEqual(self.run_command("/google 搜索一下"), [])
        self.assertEqual(self.run_command("随便聊聊"), [])
        self.assertEqual(self.run_command(""), [])

    # ---------- /go 参数校验 ----------
    # ---------- /go argument validation ----------

    def test_route_without_semicolon(self):
        replies = self.run_command("/go 北海洋 恶地")
        self.assertEqual(len(replies), 1)
        self.assertIn("分号", replies[0]["content"])

    def test_route_same_station(self):
        replies = self.run_command("/go 北海洋;北海洋")
        self.assertIn("不能相同", replies[0]["content"])

    def test_route_empty_side(self):
        replies = self.run_command("/go ;恶地")
        self.assertIn("不能为空", replies[0]["content"])

    def test_route_usage_when_empty(self):
        replies = self.run_command("/go")
        self.assertIn("格式", replies[0]["content"])

    # ---------- /go：数据源不可用时改用本地缓存 ----------
    # ---------- /go: fall back to the local cache when the data source is unavailable ----------

    def test_route_falls_back_to_cache_and_uploads(self):
        # 本机没有 1025 端口的地图服务，v4 应该抓取失败后自动回退到缓存，
        # 而不是直接失败（回退逻辑修好之前，这条会收到"寻路失败"）
        # The local machine has no map service on port 1025, so v4 should
        # automatically fall back to the cache after the fetch fails instead of
        # failing outright (before the fallback was fixed, this test received
        # "寻路失败").
        replies = self.run_command("/go 北海洋;恶地")

        self.assertEqual(replies, [], "有缓存时不应该回复错误文本")

        uploads = [r for r in HTTP_REQUESTS if "/files" in r["url"]]
        self.assertEqual(len(uploads), 1, "应该生成并上传一张图片")
        file_data = uploads[0]["json"]["file_data"]
        self.assertTrue(file_data.startswith("iVBORw0KGgo"), "上传的应是 PNG")
        self.assertGreater(len(file_data), 5000)

    def test_no_highspeed_flag_is_forwarded(self):
        recorded = []

        async def fake_run(script, *args, **kwargs):
            recorded.append((script, args))
            return types.SimpleNamespace(returncode=1, stdout="FAILED", stderr="")

        original = self.client_module.run_script
        self.client_module.run_script = fake_run
        try:
            self.run_command("/go 北海洋;恶地 --no-highspeed")
            self.assertEqual(recorded[0][0], "mtr_pathfinder_v4.py")
            self.assertIn("--no-highspeed", recorded[0][1])
        finally:
            self.client_module.run_script = original

    def test_named_line_option_becomes_no_line(self):
        recorded = []

        async def fake_run(script, *args, **kwargs):
            recorded.append(args)
            return types.SimpleNamespace(returncode=1, stdout="FAILED", stderr="")

        original = self.client_module.run_script
        self.client_module.run_script = fake_run
        try:
            self.run_command("/go 北海洋;恶地 --no-7号线")
            pair = list(recorded[0])
            index = pair.index("--no-line")
            self.assertEqual(pair[index + 1], "7号线")
        finally:
            self.client_module.run_script = original

    # ---------- /时刻表 全链路 ----------
    # ---------- /时刻表 end-to-end flow ----------

    def test_timetable_generates_image_and_uploads(self):
        replies = self.run_command("/时刻表 7号线")
        self.assertEqual(replies, [], "成功路径不应该回复错误文本")
        uploads = [r for r in HTTP_REQUESTS if "/files" in r["url"]]
        self.assertEqual(len(uploads), 1)
        self.assertTrue(uploads[0]["json"]["file_data"].startswith("iVBORw0KGgo"))

    def test_timetable_unknown_route_reports_failure(self):
        replies = self.run_command("/时刻表 根本没有这条线")
        self.assertEqual(len(replies), 1)
        self.assertIn("生成失败", replies[0]["content"])

    def test_timetable_usage_when_empty(self):
        replies = self.run_command("/时刻表")
        self.assertIn("用法", replies[0]["content"])

    # ---------- 上传失败分支 ----------
    # ---------- Upload failure branches ----------

    def test_upload_failure_is_reported(self):
        self.session_cls.responses = [(200, {})]  # 没有 file_info
        # No file_info.
        replies = self.run_command("/时刻表 7号线")
        self.assertEqual(len(replies), 1)
        self.assertIn("上传失败", replies[0]["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
