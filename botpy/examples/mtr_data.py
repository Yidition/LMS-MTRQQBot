# -*- coding: utf-8 -*-
"""mtr_timetable / mtr_diagram 共用的数据读取助手。

历史 bug：停站时间 `dwellTime` 是挂在**每个站点对象**上的（`routes[x].stations[i].dwellTime`，
单位毫秒），但两个脚本都写成 `route.get('dwellTime', ...)` 去取线路级字段。
实测 90 条线路里线路级 `dwellTime` 一个都没有、371 个站点全都有，
所以那个 `.get()` 永远返回默认值 0 —— 停站时间被整体忽略，时刻表里
"到站/发车"两行永远不会分开。
"""


def station_dwells(route, stations):
    """返回与 `stations` 等长的停站时间列表（单位：毫秒，float）。

    优先使用站点自带的 ``dwellTime``；为兼容旧数据，若线路级存在
    ``dwellTime`` 数组则整体使用它；两者都没有时返回全 0。
    任何脏数据（None / 非数字）都按 0 处理，不让排版因为缺字段崩掉。
    """
    route_level = route.get("dwellTime") if isinstance(route, dict) else None
    if isinstance(route_level, list) and route_level:
        return [_as_ms(x) for x in route_level]

    result = []
    for station in stations or []:
        value = station.get("dwellTime", 0) if isinstance(station, dict) else 0
        result.append(_as_ms(value))
    return result


def _as_ms(value):
    """把任意值安全地转成毫秒数，非法值返回 0。"""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    return number


def hex_color(value, default="#888888"):
    """把线路数据里的颜色整数安全地转成 #rrggbb，非法值用灰色兜底。"""
    try:
        return "#{:06x}".format(int(value))
    except (TypeError, ValueError):
        return default


def station_offsets(stations, durations, dwells):
    """计算每一站的 (到站偏移, 发车偏移)，单位秒。

    `durations` 是相邻两站之间的运行时间（毫秒），长度应为 ``len(stations) - 1``；
    数据缺失时按 0 处理而不是抛 IndexError。
    """
    offsets = []
    current = 0.0
    for i in range(len(stations)):
        if i > 0:
            travel = durations[i - 1] if i - 1 < len(durations) else 0
            current += _as_ms(travel) / 1000.0
        arrival = current
        dwell = dwells[i] if i < len(dwells) else 0
        departure = arrival + _as_ms(dwell) / 1000.0
        offsets.append((arrival, departure))
        current = departure
    return offsets
