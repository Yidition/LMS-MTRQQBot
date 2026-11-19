# -*- coding: utf-8 -*-
"""sm.ms 图床封装：上传图片、删除刚上传的图片、随机取一张历史图片。

历史 bug：
1. ``config['picturesToken']`` 直接下标取值 —— config.yaml 里没有这个键时
   抛 KeyError，报错信息完全看不出是配置问题；
2. 上传失败（例如文件重复）时 ``res['data']`` 是 None，``data.get()`` 直接
   AttributeError；
3. ``delete_img()`` 依赖模块级变量，没先调用 upload 就是 NameError；
4. ``open(path)`` 没有关闭文件句柄，requests 请求也没有超时。
"""

import os
import random

import requests

from botpy.ext.cog_yaml import read

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.yaml")

API_URL = "https://sm.ms/api/v2/upload"
HISTORY_URL = "https://sm.ms/api/v2/upload_history"

#: 请求超时（秒）
TIMEOUT = 30

#: 上一次 upload() 返回的删除链接（兼容原有全局变量用法）
url_delete = None


def _load_config():
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError("找不到配置文件：%s" % CONFIG_PATH)
    return read(CONFIG_PATH) or {}


def _token():
    """取出图床 token，缺失时给出可操作的提示而不是 KeyError。"""
    token = str(_load_config().get("picturesToken", "") or "").strip()
    if not token:
        raise RuntimeError(
            "config.yaml 里没有 picturesToken，图床功能不可用。\n"
            "请到 https://sm.ms/ 的 User → Dashboard → API Token 复制 Secret Token 填进去。"
        )
    return token


def _json(response):
    """解析响应体，非 JSON 时抛出带状态码的可读错误。"""
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(
            "图床返回的不是合法 JSON（HTTP %s）：%s"
            % (response.status_code, response.text[:200])
        )


def upload(path):
    """上传一张本地图片，返回图片 URL；失败抛 RuntimeError。"""
    global url_delete

    if not os.path.isfile(path):
        raise FileNotFoundError("要上传的图片不存在：%s" % path)

    headers = {"Authorization": _token()}
    with open(path, "rb") as handle:
        response = requests.post(
            API_URL, files={"smfile": handle}, headers=headers, timeout=TIMEOUT
        )

    payload = _json(response)
    if not payload.get("success"):
        # sm.ms 在"文件已存在"这类情况下 success=false，data 为 None
        raise RuntimeError("图床上传失败：%s" % (payload.get("message") or payload))

    data = payload.get("data") or {}
    url = data.get("url")
    if not url:
        raise RuntimeError("图床返回里没有图片地址：%s" % payload)

    url_delete = data.get("delete")
    print("[Info] File image URL is: " + url)
    return url


def delete_img(url=None):
    """用无头浏览器打开删除链接，把刚上传的图片删掉。

    删除链接是网页而不是 API，所以这里必须走 selenium。没装 selenium 时
    只影响本函数，不影响 upload()。
    """
    target = url or url_delete
    if not target:
        raise RuntimeError("没有可删除的图片：请先调用 upload() 或显式传入 url")

    from selenium import webdriver

    option = webdriver.ChromeOptions()
    option.add_argument("headless")

    driver = None
    try:
        driver = webdriver.Chrome(options=option)
        driver.get(target)
    finally:
        if driver is not None:
            driver.quit()


def get_upload_history():
    """随机返回一张历史上传图片的 URL。"""
    headers = {"Authorization": _token()}
    response = requests.get(
        HISTORY_URL, headers=headers, params={"page": "1"}, timeout=TIMEOUT
    )

    payload = _json(response)
    data = payload.get("data") or []
    urls = [
        item.get("url")
        for item in data
        if isinstance(item, dict) and item.get("url")
    ]
    if not urls:
        raise RuntimeError("图床没有返回任何上传历史：%s" % (payload.get("message") or payload))
    return random.choice(urls)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("用法: python img_upload.py <本地图片路径>")
    print(upload(sys.argv[1]))
    delete_img()
