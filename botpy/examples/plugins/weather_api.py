# -*- coding: utf-8 -*-
"""聚合数据天气接口封装。

历史 bug：
1. 城市名直接拼进 URL 没做编码，中文城市名会被 requests 编码成乱码或直接失败；
   改用 ``params`` 交给 requests 处理；
2. ``data['reason']`` / ``data['result']`` 全部硬下标，接口返回结构一变就 KeyError；
3. 请求没有超时，接口卡住时调用方会一直挂着。

注意：下面这个 API Key 是原作者的公开写到源码里的，建议改用环境变量
``JUHE_WEATHER_KEY`` 覆盖，并到聚合数据后台重置旧 key。

Wrapper for the Juhe weather API.

Historical bugs:
1. the city name was concatenated into the URL without encoding, so Chinese city
   names were garbled by requests or failed outright; the ``params`` argument now
   lets requests handle the encoding;
2. ``data['reason']`` / ``data['result']`` were hard-indexed, so any change in the
   response structure raised KeyError;
3. requests had no timeout, so a stuck API kept the caller hanging.

Note: the API key below was published in the source by the original author. Prefer
overriding it with the ``JUHE_WEATHER_KEY`` environment variable and reset the old
key in the Juhe console.
"""

import os

import requests

API_URL = "https://apis.juhe.cn/simpleWeather/query"

#: 聚合数据 API Key（可用环境变量覆盖）
#: Juhe API key (can be overridden by an environment variable).
API_KEY = os.environ.get("JUHE_WEATHER_KEY", "50a3bd415158e186903d6e6994157589")

#: 请求超时（秒）
#: Request timeout (seconds).
TIMEOUT = 15


def get_weather(city_name):
    """查询城市天气，返回结果字典；失败时返回 ``{'error': '...'}``。 / Query the weather of a city and return the result dict; on failure return ``{'error': '...'}``."""
    city_name = (city_name or "").strip()
    if not city_name:
        return {"error": "城市名不能为空"}

    try:
        response = requests.get(
            API_URL, params={"key": API_KEY, "city": city_name}, timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        return {"error": "请求失败：%s" % exc}

    if response.status_code != 200:
        return {"error": "请求失败，状态码: %s" % response.status_code}

    try:
        data = response.json()
    except ValueError:
        return {"error": "接口返回的不是合法 JSON"}

    if not isinstance(data, dict):
        return {"error": "接口返回格式异常"}

    reason = data.get("reason")
    if reason != "查询成功!":
        return {"error": "查询失败: %s" % (reason or data)}

    result = data.get("result")
    if not result:
        return {"error": "查询成功但没有返回天气数据"}
    return result


def format_weather(city_name):
    """把天气数据拼成一段可直接发到群里的文本。 / Render the weather data as text that can be posted to a group directly."""
    data = get_weather(city_name)
    if not isinstance(data, dict):
        return "查询失败"
    if "error" in data:
        return data["error"]

    realtime = data.get("realtime") or {}
    lines = [
        "实时天气:",
        "{info}, 温度: {temperature}℃, 湿度: {humidity}%, "
        "风向: {direct}, 风力: {power}级, AQI: {aqi}".format(
            info=realtime.get("info", "-"),
            temperature=realtime.get("temperature", "-"),
            humidity=realtime.get("humidity", "-"),
            direct=realtime.get("direct", "-"),
            power=realtime.get("power", "-"),
            aqi=realtime.get("aqi", "-"),
        ),
    ]

    future = data.get("future") or []
    if future:
        lines.append("未来几天的天气:")
        for day in future:
            if not isinstance(day, dict):
                continue
            lines.append(
                "日期: {date}, 天气: {weather}, 温度: {temperature}, 风向: {direct}".format(
                    date=day.get("date", "-"),
                    weather=day.get("weather", "-"),
                    temperature=day.get("temperature", "-"),
                    direct=day.get("direct", "-"),
                )
            )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_weather("重庆"))
