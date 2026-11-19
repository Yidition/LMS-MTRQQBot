# -*- coding: utf-8 -*-
"""bot_commands 的单元测试：命令解析、命令行构造、脚本输出判定。"""

import os
import sys
import unittest

import support

support.ensure_examples_on_path()

import bot_commands as cmds


class TestSplitNoOptions(unittest.TestCase):
    def test_plain_message(self):
        clean, args = cmds.split_no_options("/go A;B")
        self.assertEqual(clean, "/go A;B")
        self.assertEqual(args, [])

    def test_flags(self):
        clean, args = cmds.split_no_options("/go A;B --no-highspeed --no-lightrail")
        self.assertEqual(clean, "/go A;B")
        self.assertEqual(args, ["--no-highspeed", "--no-lightrail"])

    def test_named_line(self):
        clean, args = cmds.split_no_options("/go A;B --no-7号线")
        self.assertEqual(clean, "/go A;B")
        self.assertEqual(args, ["--no-line", "7号线"])

    def test_lone_prefix_is_not_a_flag(self):
        # '--no-' 后面没有内容，不应该被当成参数
        clean, args = cmds.split_no_options("/go A;B --no-")
        self.assertIn("--no-", clean)
        self.assertEqual(args, [])


class TestMatchCommand(unittest.TestCase):
    def test_route_commands(self):
        self.assertEqual(cmds.match_command("/go A;B"), ("route", "A;B"))
        self.assertEqual(cmds.match_command("/路线 A;B"), ("route", "A;B"))
        self.assertEqual(cmds.match_command("/go"), ("route", ""))

    def test_ascii_commands_need_word_boundary(self):
        # 这条是修 /go 误吞 /google 的回归测试
        self.assertEqual(cmds.match_command("/google 搜索"), (None, ""))
        self.assertEqual(cmds.match_command("/pingpong"), (None, ""))
        self.assertEqual(cmds.match_command("/ping"), ("ping", ""))
        self.assertEqual(cmds.match_command("/ping 你好"), ("ping", "你好"))

    def test_chinese_commands(self):
        self.assertEqual(cmds.match_command("/时刻表 7号线"), ("timetable", "7号线"))
        self.assertEqual(cmds.match_command("/运行图 7号线"), ("diagram", "7号线"))

    def test_unknown(self):
        self.assertEqual(cmds.match_command("随便聊聊"), (None, ""))
        self.assertEqual(cmds.match_command(""), (None, ""))


class TestParseRouteRequest(unittest.TestCase):
    def test_ok(self):
        result = cmds.parse_route_request("北海洋;恶地")
        self.assertTrue(result["ok"])
        self.assertEqual((result["start"], result["end"]), ("北海洋", "恶地"))

    def test_trims_spaces(self):
        result = cmds.parse_route_request("  北海洋 ; 恶地  ")
        self.assertEqual((result["start"], result["end"]), ("北海洋", "恶地"))

    def test_semicolon_uses_first_occurrence(self):
        result = cmds.parse_route_request("A;B;C")
        self.assertEqual((result["start"], result["end"]), ("A", "B;C"))

    def test_missing_semicolon(self):
        result = cmds.parse_route_request("北海洋 恶地")
        self.assertFalse(result["ok"])
        self.assertIn("分号", result["error"])

    def test_empty_side(self):
        for text in (";恶地", "北海洋;", ";"):
            result = cmds.parse_route_request(text)
            self.assertFalse(result["ok"], text)
            self.assertIn("不能为空", result["error"])

    def test_same_station(self):
        result = cmds.parse_route_request("北海洋;北海洋")
        self.assertFalse(result["ok"])
        self.assertIn("不能相同", result["error"])

    def test_empty_input(self):
        self.assertIn("格式", cmds.parse_route_request("")["error"])


class TestScriptCommand(unittest.TestCase):
    def test_uses_current_interpreter_not_py_launcher(self):
        # 修的是 client.py 里写死 ['py', ...] 的 bug：py 指向的解释器
        # 和跑机器人的解释器可能不是同一个，会缺依赖
        command = cmds.build_script_command("mtr_diagram.py", "7号线")
        self.assertEqual(command[0], sys.executable)
        self.assertNotEqual(os.path.basename(command[0]).lower(), "py.exe")
        self.assertEqual(command[1], "-B")
        self.assertTrue(command[2].endswith("mtr_diagram.py"))
        self.assertEqual(command[3:], ["7号线"])

    def test_env_override(self):
        old = os.environ.get("MTR_PYTHON")
        os.environ["MTR_PYTHON"] = r"C:\fake\python.exe"
        try:
            command = cmds.build_script_command("x.py")
            self.assertEqual(command[0], r"C:\fake\python.exe")
        finally:
            if old is None:
                os.environ.pop("MTR_PYTHON", None)
            else:
                os.environ["MTR_PYTHON"] = old

    def test_absolute_script_path_kept(self):
        command = cmds.build_script_command(r"C:\tmp\x.py")
        self.assertEqual(command[2], r"C:\tmp\x.py")


class TestChildEnv(unittest.TestCase):
    def test_forces_utf8(self):
        env = cmds.child_env()
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")


class TestInterpretResult(unittest.TestCase):
    def test_success_contract(self):
        ok, detail = cmds.interpret_result("SUCCESS:out.png", "")
        self.assertTrue(ok)
        self.assertEqual(detail, "")

    def test_failure_prefers_stderr(self):
        ok, detail = cmds.interpret_result("ERROR: 线路不存在", "Traceback: boom\nFAILED")
        self.assertFalse(ok)
        self.assertIn("boom", detail)
        self.assertNotIn("FAILED", detail)

    def test_failure_falls_back_to_stdout(self):
        ok, detail = cmds.interpret_result("ERROR: 找不到线路\nFAILED", "")
        self.assertFalse(ok)
        self.assertIn("找不到线路", detail)

    def test_empty_output_mentions_returncode(self):
        ok, detail = cmds.interpret_result("", "", returncode=2)
        self.assertFalse(ok)
        self.assertIn("2", detail)

    def test_detail_is_truncated(self):
        ok, detail = cmds.interpret_result("x" * 2000, "")
        self.assertFalse(ok)
        self.assertLessEqual(len(detail), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
