# -*- coding: utf-8 -*-
"""logging_setup 的测试：落盘、UTF-8、请求 id、轮转、级别、降级、装饰器。 / Tests for logging_setup: file output, UTF-8, request id, rotation, levels, degrade, and the decorator."""

import asyncio
import io
import logging
import os
import shutil
import tempfile
import types
import unittest

import support

support.ensure_examples_on_path()

import logging_setup


def _flush():
    """断言文件内容前先把处理器缓冲刷出去。 / Flush the handler buffers before asserting on file content."""
    for handler in logging.getLogger(logging_setup.ROOT_LOGGER).handlers:
        try:
            handler.flush()
        except Exception:
            pass


def _read(path):
    _flush()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class LoggingTestCase(unittest.TestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp(prefix="mtr-log-")
        for key in (
            logging_setup.ENV_LEVEL,
            logging_setup.ENV_CONSOLE,
            logging_setup.ENV_MAX_BYTES,
            logging_setup.ENV_BACKUPS,
        ):
            os.environ.pop(key, None)
        os.environ[logging_setup.ENV_DIR] = self.log_dir
        self.log_path = os.path.join(self.log_dir, "bot.log")

    def tearDown(self):
        # 先换成控制台配置，避免处理器还指着即将删除的目录
        # Switch to the console configuration first so no handler still points
        # at the directory about to be deleted.
        logging_setup.setup_console()
        os.environ.pop(logging_setup.ENV_DIR, None)
        shutil.rmtree(self.log_dir, ignore_errors=True)

    def setup_logging(self, **kwargs):
        kwargs.setdefault("log_dir", self.log_dir)
        kwargs.setdefault("merge_botpy", False)
        kwargs.setdefault("console_stream", io.StringIO())
        return logging_setup.setup(**kwargs)


class TestFileOutput(LoggingTestCase):
    def test_writes_chinese_as_utf8(self):
        logger = self.setup_logging()
        logger.info("中文日志测试 %s", "参数")
        text = _read(self.log_path)
        self.assertIn("中文日志测试", text)
        self.assertIn("参数", text)

    def test_line_has_level_module_and_time(self):
        logger = self.setup_logging()
        logger.warning("hello")
        line = _read(self.log_path).strip().splitlines()[-1]
        self.assertIn("WARNING", line)
        # 格式里要能看出是哪个文件哪一行发的，否则日志没法定位
        # The format must reveal which file and line emitted the record,
        # otherwise the log cannot be used to locate problems.
        self.assertIn("test_logging.py", line)
        self.assertRegex(line, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_respects_log_file_name(self):
        logger = self.setup_logging(log_file="other.log")
        logger.info("x")
        self.assertTrue(os.path.isfile(os.path.join(self.log_dir, "other.log")))

    def test_makes_missing_directory(self):
        nested = os.path.join(self.log_dir, "a", "b")
        logger = self.setup_logging(log_dir=nested)
        logger.info("x")
        self.assertTrue(os.path.isfile(os.path.join(nested, "bot.log")))


class TestLevels(LoggingTestCase):
    def test_default_level_is_info(self):
        logger = self.setup_logging()
        self.assertTrue(logger.isEnabledFor(logging.INFO))
        self.assertFalse(logger.isEnabledFor(logging.DEBUG))

    def test_env_sets_level(self):
        os.environ[logging_setup.ENV_LEVEL] = "DEBUG"
        logger = self.setup_logging()
        self.assertTrue(logger.isEnabledFor(logging.DEBUG))

    def test_numeric_level(self):
        self.assertEqual(logging_setup.resolve_level("10"), 10)
        self.assertEqual(logging_setup.resolve_level("error"), logging.ERROR)
        self.assertEqual(logging_setup.resolve_level(None), logging.INFO)
        self.assertEqual(logging_setup.resolve_level("nonsense"), logging.INFO)

    def test_console_default_is_warning(self):
        # 子进程的 stderr 是 client 判断失败的依据，默认不能被 INFO 污染
        # The subprocess stderr is what client uses to judge failure, so it must
        # not be polluted with INFO output by default.
        logger = logging_setup.setup_console()
        self.assertEqual(logger.getEffectiveLevel(), logging.WARNING)
        self.assertFalse(logger.isEnabledFor(logging.INFO))

    def test_console_level_env(self):
        os.environ[logging_setup.ENV_CONSOLE] = "INFO"
        logger = logging_setup.setup_console(stream=io.StringIO())
        self.assertTrue(logger.isEnabledFor(logging.INFO))

    def test_console_stream_receives_only_warnings(self):
        stream = io.StringIO()
        logger = self.setup_logging(console_stream=stream)
        logger.info("不该出现")
        logger.warning("应该出现")
        output = stream.getvalue()
        self.assertNotIn("不该出现", output)
        self.assertIn("应该出现", output)


class TestRequestId(LoggingTestCase):
    def test_default_id_is_dash(self):
        self.assertEqual(logging_setup.current_request_id(), "-")

    def test_seed_uses_tail(self):
        with logging_setup.request_context("ABCDEF12345678") as reqid:
            self.assertEqual(reqid, "12345678")

    def test_random_id_without_seed(self):
        with logging_setup.request_context("") as reqid:
            self.assertEqual(len(reqid), 8)

    def test_id_in_log_line(self):
        logger = self.setup_logging()
        with logging_setup.request_context("MSGID00000000A1"):
            logger.info("带请求 id 的日志")
        line = [l for l in _read(self.log_path).splitlines() if "带请求 id" in l][-1]
        self.assertIn("[000000A1]", line)

    def test_id_restored_after_context(self):
        with logging_setup.request_context("abcdefgh1234"):
            self.assertEqual(logging_setup.current_request_id(), "efgh1234")
        self.assertEqual(logging_setup.current_request_id(), "-")


class TestIdempotency(LoggingTestCase):
    def test_setup_twice_does_not_duplicate_lines(self):
        logger = self.setup_logging()
        logger.info("第一次")
        self.setup_logging()
        logger.info("第二次")
        lines = _read(self.log_path).splitlines()
        # 第二次 setup 后每条日志只能出现一次（处理器没被重复添加）
        # After the second setup each log record must appear only once (no
        # handler was added twice).
        self.assertEqual(len([l for l in lines if "第一次" in l]), 1, lines)
        self.assertEqual(len([l for l in lines if "第二次" in l]), 1, lines)

    def test_setup_twice_keeps_one_file_handler(self):
        self.setup_logging()
        logger = self.setup_logging()
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        self.assertEqual(len(file_handlers), 1)


class TestRotation(LoggingTestCase):
    def test_rotation_creates_backup(self):
        logger = self.setup_logging(max_bytes=160, backups=2)
        for i in range(30):
            logger.info("填充日志内容 %02d %s", i, "x" * 20)
        backups = [n for n in os.listdir(self.log_dir) if n.startswith("bot.log.")]
        self.assertTrue(backups, os.listdir(self.log_dir))

    def test_backup_count_respected(self):
        logger = self.setup_logging(max_bytes=120, backups=2)
        for i in range(200):
            logger.info("内容 %03d %s", i, "y" * 30)
        backups = [n for n in os.listdir(self.log_dir) if n.startswith("bot.log.")]
        self.assertLessEqual(len(backups), 2)


class TestDegrade(LoggingTestCase):
    def test_unwritable_dir_falls_back_to_console(self):
        blocker = os.path.join(self.log_dir, "not-a-dir")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")

        stream = io.StringIO()
        logger = logging_setup.setup(
            log_dir=blocker, console_stream=stream, merge_botpy=False
        )
        self.assertEqual(
            [h for h in logger.handlers if isinstance(h, logging.FileHandler)], []
        )
        logger.warning("降级告警")
        self.assertIn("降级告警", stream.getvalue())


class TestTraced(unittest.TestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp(prefix="mtr-trace-")
        os.environ[logging_setup.ENV_DIR] = self.log_dir
        logging_setup.setup(log_dir=self.log_dir, merge_botpy=False,
                            console_stream=io.StringIO())
        self.log_path = os.path.join(self.log_dir, "bot.log")

    def tearDown(self):
        logging_setup.setup_console()
        os.environ.pop(logging_setup.ENV_DIR, None)
        shutil.rmtree(self.log_dir, ignore_errors=True)

    def _message(self):
        return types.SimpleNamespace(
            id="MSGID0000000001",
            group_openid="GROUP1",
            author=types.SimpleNamespace(member_openid="USER1"),
        )

    def test_logs_start_and_end_with_same_reqid(self):
        calls = []

        @logging_setup.traced
        async def handler(self, message):
            calls.append(logging_setup.current_request_id())

        asyncio.run(handler(object(), self._message()))

        text = _read(self.log_path)
        start = [l for l in text.splitlines() if "收到消息" in l]
        end = [l for l in text.splitlines() if "消息处理结束" in l]
        self.assertEqual(len(start), 1)
        self.assertEqual(len(end), 1)
        self.assertIn("GROUP1", start[0])
        self.assertIn("USER1", start[0])
        self.assertIn("[00000001]", start[0])
        self.assertIn("[00000001]", end[0])
        self.assertEqual(calls, ["00000001"])

    def test_exception_is_logged_and_reraised(self):
        @logging_setup.traced
        async def handler(self, message):
            raise RuntimeError("炸了")

        with self.assertRaises(RuntimeError):
            asyncio.run(handler(object(), self._message()))

        text = _read(self.log_path)
        self.assertIn("处理消息抛出异常", text)
        self.assertIn("炸了", text)


class TestClientWiring(unittest.TestCase):
    """client.py 无法在本环境 import（缺 botpy），只能做源码约束检查。 / client.py cannot be imported in this environment (botpy is missing), so only source contract checks are possible."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(support.EXAMPLES_DIR, "client.py"), encoding="utf-8") as f:
            cls.source = f.read()

    def test_client_uses_shared_setup(self):
        self.assertIn("logging_setup.setup(", self.source)
        self.assertNotIn("from botpy import logging", self.source)

    def test_handler_is_traced(self):
        self.assertIn("@logging_setup.traced", self.source)

    def test_scripts_setup_console(self):
        for name in ("mtr_timetable.py", "mtr_diagram.py", "mtr_pathfinder_v4.py"):
            with open(os.path.join(support.EXAMPLES_DIR, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("logging_setup.setup_console()", text, name)


class TestRunScriptLogging(unittest.TestCase):
    """真跑一次 script_runner，验证子进程日志完整落盘。 / Run script_runner for real once to verify that subprocess logs land in the file completely."""

    def setUp(self):
        self.log_dir = tempfile.mkdtemp(prefix="mtr-run-")
        self.out_dir = tempfile.mkdtemp(prefix="mtr-out-")
        os.environ[logging_setup.ENV_DIR] = self.log_dir
        logging_setup.setup(log_dir=self.log_dir, merge_botpy=False,
                            console_stream=io.StringIO())
        self.log_path = os.path.join(self.log_dir, "bot.log")

    def tearDown(self):
        logging_setup.setup_console()
        os.environ.pop(logging_setup.ENV_DIR, None)
        shutil.rmtree(self.log_dir, ignore_errors=True)
        shutil.rmtree(self.out_dir, ignore_errors=True)

    def test_successful_run_is_logged(self):
        import script_runner

        out = os.path.join(self.out_dir, "tt.png")
        result = asyncio.run(
            script_runner.run_script("mtr_timetable.py", "7号线", "--output", out)
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SUCCESS", result.stdout)

        text = _read(self.log_path)
        self.assertIn("执行外部脚本 script=mtr_timetable.py", text)
        # 关键：耗时、返回码、输出大小都记下来了
        # The key point: duration, return code, and output size are all logged.
        self.assertRegex(text, r"脚本结束 script=mtr_timetable\.py rc=0 耗时=\d+ms stdout=\d+B")

    def test_failed_run_is_logged_with_reason(self):
        import script_runner

        out = os.path.join(self.out_dir, "none.png")
        result = asyncio.run(
            script_runner.run_script("mtr_timetable.py", "根本没有这条线", "--output", out)
        )

        self.assertEqual(result.returncode, 1)
        text = _read(self.log_path)
        self.assertIn("脚本以非 0 退出 script=mtr_timetable.py rc=1", text)

    def test_full_output_kept_at_debug_level(self):
        import script_runner

        logging_setup.setup(level="DEBUG", log_dir=self.log_dir, merge_botpy=False,
                            console_stream=io.StringIO())
        out = os.path.join(self.out_dir, "dbg.png")
        asyncio.run(script_runner.run_script("mtr_timetable.py", "7号线", "--output", out))

        text = _read(self.log_path)
        # 回给用户的消息只保留 300 字符，完整原文必须能在日志里找到
        # Only 300 characters are kept in the reply to the user, so the full
        # original output must be findable in the log.
        self.assertIn("stdout of mtr_timetable.py", text)
        self.assertIn("SUCCESS:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
