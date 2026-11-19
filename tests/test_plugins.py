# -*- coding: utf-8 -*-
"""插件层测试：待办读写、图床取 token、天气格式化、模块导入无副作用。 / Plugin-layer tests: todo read/write, image-host token retrieval, weather formatting, and side-effect-free module imports."""

import os
import shutil
import sys
import tempfile
import unittest

import support

support.ensure_examples_on_path()

PLUGINS_DIR = os.path.join(support.EXAMPLES_DIR, "plugins")


def setUpModule():
    support.stub_botpy()


class TestUserTodoList(unittest.TestCase):
    """待办以前写死 '..\\examples\\user_data\\'，从 examples 启动时目录根本不存在。 / The todo path used to be hard-coded as '..\\examples\\user_data\\', and that directory does not exist at all when started from examples."""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = tempfile.mkdtemp(prefix="mtr-todo-")
        os.environ["MTR_USER_DATA_DIR"] = cls.data_dir
        import plugins.user_todo_list as todo
        todo.DATA_DIR = cls.data_dir
        cls.todo = todo

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("MTR_USER_DATA_DIR", None)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def setUp(self):
        for name in os.listdir(self.data_dir):
            os.remove(os.path.join(self.data_dir, name))

    def test_show_missing_user_creates_file(self):
        result = self.todo.show("user1")
        self.assertEqual(result, -1)
        self.assertTrue(os.path.isfile(os.path.join(self.data_dir, "user1.json")))

    def test_insert_then_show(self):
        self.todo.show("user2")
        self.assertEqual(self.todo.insert("user2", "写作业"), 1)
        self.assertEqual(self.todo.insert("user2", "打游戏"), 1)
        self.assertEqual(self.todo.show("user2"), ["写作业", "打游戏"])

    def test_insert_replaces_empty_hint(self):
        seed = os.path.join(self.data_dir, "user3.json")
        with open(seed, "w", encoding="utf-8") as handle:
            handle.write('{"ToDo": ["还没有待办qwq"]}')
        self.todo.insert("user3", "第一件事")
        self.assertEqual(self.todo.show("user3"), ["第一件事"])

    def test_delete_by_index(self):
        self.todo.show("user4")
        self.todo.insert("user4", "a")
        self.todo.insert("user4", "b")
        self.assertEqual(self.todo.delete("user4", 1), 1)
        self.assertEqual(self.todo.show("user4"), ["b"])

    def test_delete_out_of_range(self):
        self.todo.show("user5")
        self.todo.insert("user5", "only")
        self.assertEqual(self.todo.delete("user5", 9), -2)
        self.assertEqual(self.todo.delete("user5", 0), -2)
        self.assertEqual(self.todo.show("user5"), ["only"])

    def test_delete_last_item_keeps_placeholder(self):
        self.todo.show("user6")
        self.todo.insert("user6", "唯一一条")
        self.assertEqual(self.todo.delete("user6", 1), 1)
        self.assertEqual(self.todo.show("user6"), [self.todo.EMPTY_HINT])

    def test_init_resets(self):
        self.todo.show("user7")
        self.todo.insert("user7", "x")
        self.assertEqual(self.todo.init("user7"), 1)
        self.assertEqual(self.todo.show("user7"), [self.todo.EMPTY_HINT])

    def test_filename_is_sanitized(self):
        self.todo.show("a/b\\c")
        names = os.listdir(self.data_dir)
        self.assertIn("a_b_c.json", names)

    def test_empty_user_name_rejected(self):
        with self.assertRaises(ValueError):
            self.todo.show("   ")


class TestImgUploadToken(unittest.TestCase):
    """原来 config['picturesToken'] 缺键会抛 KeyError，现在要给出可操作的提示。 / A missing config['picturesToken'] key used to raise KeyError; now it must give an actionable hint."""

    @classmethod
    def setUpClass(cls):
        import plugins.img_upload as module
        cls.module = module
        cls.original = module.CONFIG_PATH
        cls.tmp = tempfile.mkdtemp(prefix="mtr-cfg-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.module.CONFIG_PATH = self.original

    def _write_config(self, text):
        path = os.path.join(self.tmp, "config.yaml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.module.CONFIG_PATH = path
        return path

    def test_missing_token_raises_readable_error(self):
        self._write_config('appid: "1"\nsecret: "2"\n')
        with self.assertRaises(RuntimeError) as ctx:
            self.module._token()
        self.assertIn("picturesToken", str(ctx.exception))

    def test_missing_config_file(self):
        self.module.CONFIG_PATH = os.path.join(self.tmp, "nope.yaml")
        with self.assertRaises(RuntimeError):
            self.module._token()

    def test_token_returned(self):
        self._write_config('picturesToken: "abc123"\n')
        self.assertEqual(self.module._token(), "abc123")

    def test_upload_missing_file_raises(self):
        self._write_config('picturesToken: "abc123"\n')
        with self.assertRaises(FileNotFoundError):
            self.module.upload(os.path.join(self.tmp, "not-here.png"))

    def test_delete_img_without_url_raises(self):
        self.module.url_delete = None
        with self.assertRaises(RuntimeError):
            self.module.delete_img()


class TestWeatherFormatting(unittest.TestCase):
    def setUp(self):
        import plugins.weather_api as module
        self.module = module
        self.original = module.get_weather

    def tearDown(self):
        self.module.get_weather = self.original

    def test_formats_realtime_and_future(self):
        self.module.get_weather = lambda city: {
            "realtime": {"info": "晴", "temperature": "25", "humidity": "40",
                         "direct": "东风", "power": "2", "aqi": "30"},
            "future": [{"date": "2026-11-18", "weather": "多云",
                        "temperature": "18/26", "direct": "东风"}],
        }
        text = self.module.format_weather("重庆")
        self.assertIn("晴", text)
        self.assertIn("25℃", text)
        self.assertIn("2026-11-18", text)

    def test_error_passthrough(self):
        self.module.get_weather = lambda city: {"error": "查询失败: 城市不存在"}
        self.assertEqual(self.module.format_weather("火星"), "查询失败: 城市不存在")

    def test_missing_fields_do_not_raise(self):
        self.module.get_weather = lambda city: {"realtime": {}}
        text = self.module.format_weather("重庆")
        self.assertIn("实时天气", text)

    def test_get_weather_rejects_empty_city(self):
        self.assertIn("error", self.module.get_weather(""))


class TestWebScreenShotNoSideEffect(unittest.TestCase):
    """原来 import 这个模块就会拉起 Chrome，现在导入必须无副作用。 / Importing this module used to launch Chrome; now the import must have no side effects."""

    def test_import_is_side_effect_free(self):
        import plugins.web_screen_shot as module
        self.assertTrue(callable(module.screenshot))
        self.assertTrue(module.IMGS_DIR.endswith(os.path.join("examples", "imgs")))

    def test_screenshot_requires_selenium_lazily(self):
        try:
            import selenium  # noqa: F401
        except ImportError:
            pass
        else:
            self.skipTest("本机装了 selenium，不测缺依赖的分支")

        import plugins.web_screen_shot as module
        with self.assertRaises(ImportError):
            module.screenshot("https://example.com")


class TestFortuneModule(unittest.TestCase):
    """模型要真的是 declarative 模型，数据库路径要绝对。 / The models must really be declarative models, and the database path must be absolute."""

    def test_models_are_registered(self):
        import plugins.fortune_by_sqlite as module
        self.assertTrue(hasattr(module.QrFortune, "__table__"))
        self.assertTrue(hasattr(module.QrFortuneLog, "__table__"))
        self.assertTrue(os.path.isabs(module.DB_PATH))
        self.assertTrue(module.DB_PATH.endswith("chat_bot.db"))
        self.assertTrue(os.path.isabs(module.INIT_SCRIPT))

    def test_today_query_uses_local_time(self):
        import plugins.fortune_by_sqlite as module
        sql = str(module.selectFortuneLog)
        self.assertIn("localtime", sql)


if __name__ == "__main__":
    unittest.main(verbosity=2)
