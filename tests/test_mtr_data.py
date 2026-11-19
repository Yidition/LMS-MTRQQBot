# -*- coding: utf-8 -*-
"""mtr_data 的单元测试，并用真实缓存数据校验"停站时间在站点上"这个前提。 / Unit tests for mtr_data, plus validation of the "dwell time lives on stations" premise against real cache data."""

import json
import os
import unittest

import support

support.ensure_examples_on_path()

from mtr_data import hex_color, station_dwells, station_offsets

CACHE = os.path.join(support.EXAMPLES_DIR, support.CACHE_FILES[0])


def load_cache():
    with open(CACHE, encoding="utf-8") as handle:
        return json.load(handle)


class TestRealDataShape(unittest.TestCase):
    """这些断言记录的是当初 bug 的根因，数据格式变了要立刻发现。 / These assertions record the root cause of the original bug, so any change in the data format is noticed immediately."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_cache()

    def test_dwell_time_lives_on_stations_not_routes(self):
        routes = self.data["routes"]
        route_level = [r for r in routes.values() if isinstance(r.get("dwellTime"), list)]
        self.assertEqual(route_level, [], "线路级 dwellTime 不应该存在，停站时间在站点上")

        total = with_dwell = 0
        for route in routes.values():
            for station in route["stations"]:
                total += 1
                if "dwellTime" in station:
                    with_dwell += 1
        self.assertGreater(total, 0)
        self.assertEqual(total, with_dwell)

    def test_station_dwells_is_not_all_zero(self):
        route = next(iter(self.data["routes"].values()))
        dwells = station_dwells(route, route["stations"])
        self.assertEqual(len(dwells), len(route["stations"]))
        self.assertTrue(any(d > 0 for d in dwells), "停站时间不应全为 0")


class TestStationDwells(unittest.TestCase):
    def test_reads_station_field(self):
        route = {"stations": [{"dwellTime": 10000}, {"dwellTime": 500}]}
        self.assertEqual(station_dwells(route, route["stations"]), [10000.0, 500.0])

    def test_route_level_list_is_used_as_fallback(self):
        route = {"dwellTime": [1000, 2000]}
        stations = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(station_dwells(route, stations), [1000.0, 2000.0])

    def test_dirty_values_become_zero(self):
        route = {"stations": [{"dwellTime": None}, {"dwellTime": "abc"}, {"dwellTime": -5}, {}]}
        self.assertEqual(station_dwells(route, route["stations"]), [0.0, 0.0, 0.0, 0.0])

    def test_empty_input(self):
        self.assertEqual(station_dwells({}, []), [])


class TestStationOffsets(unittest.TestCase):
    def test_dwell_separates_arrival_and_departure(self):
        stations = [{}, {}, {}]
        durations = [1000, 2000]          # 毫秒
        # Milliseconds.
        dwells = [0, 10000, 0]            # 中间站停 10 秒
        # The middle station dwells for 10 seconds.
        offsets = station_offsets(stations, durations, dwells)

        self.assertEqual(offsets[0], (0.0, 0.0))
        # 第一站到第二站运行 1 秒
        # Running from the first station to the second takes 1 second.
        self.assertAlmostEqual(offsets[1][0], 1.0)
        # 停站 10 秒
        # Dwell for 10 seconds.
        self.assertAlmostEqual(offsets[1][1], 11.0)
        # 再运行 2 秒
        # Then run for another 2 seconds.
        self.assertAlmostEqual(offsets[2][0], 13.0)

    def test_short_durations_do_not_raise(self):
        offsets = station_offsets([{}, {}, {}], [1000], [0, 0, 0])
        self.assertEqual(len(offsets), 3)
        self.assertAlmostEqual(offsets[2][0], 1.0)   # 缺失的时长按 0 处理
        # Missing durations are treated as 0.

    def test_missing_dwells_do_not_raise(self):
        offsets = station_offsets([{}, {}], [500], [])
        self.assertAlmostEqual(offsets[1][0], 0.5)
        self.assertAlmostEqual(offsets[1][1], 0.5)


class TestHexColor(unittest.TestCase):
    def test_int(self):
        self.assertEqual(hex_color(0xE2002C), "#e2002c")

    def test_invalid(self):
        self.assertEqual(hex_color(None), "#888888")
        self.assertEqual(hex_color("oops"), "#888888")


if __name__ == "__main__":
    unittest.main(verbosity=2)
