# -*- coding: utf-8 -*-
"""网页整页截图小工具（依赖 selenium + chromedriver）。

历史 bug：
1. 导入本模块就会启动一个 Chrome 浏览器 —— 任何 ``import plugins.web_screen_shot``
   都会拉起浏览器进程，而且没装 selenium 时直接 ImportError；
2. 输出路径写死 ``'../imgs/webpage.png'``，只有 cwd 恰好是 plugins/ 时才成立；
3. 用完不调 ``driver.quit()``，chrome 进程会一直挂着。

现在改成函数式：导入无副作用，调用时才启动浏览器，路径基于 ``__file__``。
"""

import os

from PIL import Image

#: 截图默认保存目录
IMGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "imgs")
)

#: 默认目标网页
DEFAULT_URL = "https://www.wenku8.net/book/2331.htm"


def screenshot(url=DEFAULT_URL, output_path=None):
    """对整个网页截图，返回保存路径。"""
    from selenium import webdriver  # 延迟导入：没装 selenium 也不影响导入本模块

    output_path = output_path or os.path.join(IMGS_DIR, "webpage.png")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    option = webdriver.ChromeOptions()
    option.add_argument("headless")

    width = height = None
    driver = None
    try:
        driver = webdriver.Chrome(options=option)
        driver.get(url)
        width = driver.execute_script("return document.documentElement.scrollWidth")
        height = driver.execute_script("return document.documentElement.scrollHeight")
        # 窗口必须先把高度撑开，否则截图只有首屏
        driver.set_window_size(width, height)
        driver.get_screenshot_as_file(output_path)
    finally:
        if driver is not None:
            driver.quit()

    print("整个网页尺寸:height={},width={}".format(height, width))
    with Image.open(output_path) as image:
        print("截图尺寸:height={},width={}".format(image.size[1], image.size[0]))
    return output_path


if __name__ == "__main__":
    screenshot()
