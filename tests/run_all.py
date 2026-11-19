# -*- coding: utf-8 -*-
"""跑全部测试：python -B tests\\run_all.py

退出码 0 表示全绿。
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True


def main():
    suite = unittest.TestLoader().discover(HERE, pattern="test_*.py", top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print("\n" + "=" * 60)
    print("共 %d 项：失败 %d，错误 %d，跳过 %d" % (
        result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
    print("=" * 60)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
