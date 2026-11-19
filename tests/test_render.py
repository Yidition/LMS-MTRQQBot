# -*- coding: utf-8 -*-
"""端到端集成测试：真的跑三个出图脚本，断言产物是有效 PNG。

这些测试跑在一个临时的"仿真工作目录"里（含缓存 json 与 mtr_pathfinder_data），
因为脚本用的都是相对 cwd 的路径。目录本身就不在 examples 下，
顺带也验证了 raqm DLL 注册修复——否则 draw_text_v2 会抛
"not supported without libraqm"。
"""

import ast
import os
import subprocess
import sys
import unittest

import support

EXAMPLES = support.EXAMPLES_DIR


def run_script(script, *args, cwd, timeout=300):
    command = [sys.executable, "-B", os.path.join(EXAMPLES, script)] + list(args)
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=support.child_env(),
        timeout=timeout,
    )


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = support.workspace()
        cls.out_dir = os.path.join(cls.work, "out")
        os.makedirs(cls.out_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        support.cleanup_workspace()

    def assert_png(self, path, min_bytes=3000):
        self.assertTrue(os.path.isfile(path), "没有生成产物：%s" % path)
        self.assertGreater(os.path.getsize(path), min_bytes, "产物太小：%s" % path)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n", "不是合法 PNG")

    def test_raqm_available_from_foreign_cwd(self):
        code = (
            "import sys; sys.path.insert(0, r'%s'); "
            "import raqm_support; print(raqm_support.raqm_available())" % EXAMPLES
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=self.work,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=support.child_env(),
        )
        self.assertEqual(result.stdout.strip(), "True", result.stderr)

    def test_timetable(self):
        out = os.path.join(self.out_dir, "timetable.png")
        result = run_script(
            "mtr_timetable.py", "7号线", "--output", out, "--max-trains", "5", cwd=self.work
        )
        self.assertIn("SUCCESS", result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assert_png(out)

    def test_diagram(self):
        out = os.path.join(self.out_dir, "diagram.png")
        result = run_script(
            "mtr_diagram.py", "7号线", "--output", out, "--max-trains", "8", cwd=self.work
        )
        self.assertIn("SUCCESS", result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assert_png(out)

    def test_pathfinder(self):
        out = os.path.join(self.out_dir, "route.png")
        result = run_script(
            "mtr_pathfinder_v4.py", "北海洋", "恶地",
            "--no-update", "--output", out, cwd=self.work
        )
        self.assertIn("SUCCESS", result.stdout, result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assert_png(out, min_bytes=10000)

    def test_pathfinder_falls_back_to_cache(self):
        """地图服务没开时，只要本地有缓存就应该照常出图。

        这里故意不传 --no-update，模拟机器人默认行为（先抓在线数据）。
        修复前这种情况会直接失败，缓存形同虚设。
        """
        import socket

        out = os.path.join(self.out_dir, "fallback.png")
        result = run_script(
            "mtr_pathfinder_v4.py", "北海洋", "恶地", "--output", out, cwd=self.work
        )

        self.assertIn("SUCCESS", result.stdout, result.stderr)
        self.assert_png(out, min_bytes=10000)

        with socket.socket() as probe:
            server_up = probe.connect_ex(("127.0.0.1", 1025)) == 0
        if not server_up:
            self.assertIn("改用本地缓存", result.stdout)

    def test_diagram_reports_degenerate_route_clearly(self):
        """单站环线这类退化数据要给出准确原因，而不是"没有找到发车时间"。"""
        out = os.path.join(self.out_dir, "degenerate.png")
        result = run_script(
            "mtr_diagram.py", "YRT轻铁|YRT Light Rail||Y01", "--output", out, cwd=self.work
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("站序数据异常", result.stdout)

    def test_pathfinder_unknown_station_reports_failure(self):
        out = os.path.join(self.out_dir, "bad.png")
        result = run_script(
            "mtr_pathfinder_v4.py", "不存在的车站XYZ", "恶地",
            "--no-update", "--output", out, cwd=self.work
        )
        self.assertNotIn("SUCCESS", result.stdout)
        # 三个出图脚本的失败退出码要一致（原来 v4 失败也退出 0）
        self.assertEqual(result.returncode, 1)
        self.assertFalse(os.path.isfile(out))

    def test_timetable_unknown_route_reports_failure(self):
        out = os.path.join(self.out_dir, "bad_timetable.png")
        result = run_script(
            "mtr_timetable.py", "根本没有这条线", "--output", out, cwd=self.work
        )
        self.assertNotIn("SUCCESS", result.stdout)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR", result.stdout)


class ClientSourceTests(unittest.TestCase):
    """client.py 依赖 botpy 无法在此环境运行，退而校验它的源码约束。"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(EXAMPLES, "client.py"), encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_source_parses(self):
        ast.parse(self.source)

    def test_no_hardcoded_py_launcher(self):
        # 原来 cmd = ['py', ...] 会用到 py launcher 的默认解释器（3.15），
        # 和跑机器人的 3.8 不是同一个，缺一堆依赖
        self.assertNotIn("['py',", self.source)
        with open(os.path.join(EXAMPLES, "script_runner.py"), encoding="utf-8") as handle:
            runner = handle.read()
        self.assertIn("build_script_command", runner)

    def test_uses_current_interpreter(self):
        self.assertIn("sys.executable", open(
            os.path.join(EXAMPLES, "bot_commands.py"), encoding="utf-8").read())

    def test_subprocess_configured_for_utf8(self):
        # 跑子进程的逻辑已抽到 script_runner.py
        with open(os.path.join(EXAMPLES, "script_runner.py"), encoding="utf-8") as handle:
            runner = handle.read()
        self.assertIn("child_env", runner)
        self.assertIn("errors=\"replace\"", runner)

    def test_scripts_run_in_examples_dir(self):
        with open(os.path.join(EXAMPLES, "script_runner.py"), encoding="utf-8") as handle:
            runner = handle.read()
        self.assertIn("cwd=cmds.EXAMPLES_DIR", runner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
