# -*- coding: utf-8 -*-
"""基于 SQLAlchemy + SQLite 的"今日运势"。

历史 bug：
1. ``class QrFortune:`` / ``class QrFortuneLog:`` 没有继承 ``Base``，SQLAlchemy
   压根没把它们注册成模型（目前只用原生 SQL 所以没暴露，但一旦走 ORM 就报
   "Class does not have a __table__"）；
2. 数据库路径 ``sqlite:///./chat_bot.db`` 相对 cwd，换个目录启动就静默新建一个空库；
3. 判重用 ``date('now')`` 取的是 **UTC** 日期，东八区 8 点前会被算成"昨天"，
   同一个人一天能抽到两次运势；
4. ``execute_init_file`` 硬编码 ``"python"``，可能和跑机器人的解释器不是同一个；
5. 表为空时 ``get_fortune()`` 返回 None，随后 ``result.fortune_summary``
   直接 AttributeError；
6. ``echo=True`` 把每条 SQL 都打进日志。
"""

import os
import subprocess
import sys

from sqlalchemy import Column, Integer, String, Date, create_engine, text
from sqlalchemy.orm import sessionmaker

try:  # SQLAlchemy >= 1.4
    from sqlalchemy.orm import declarative_base
except ImportError:  # SQLAlchemy 1.3 及更早：declarative_base 在 ext 里
    from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

#: 本文件所在目录（plugins/）与 examples/ 根目录
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.abspath(os.path.join(PLUGIN_DIR, ".."))

#: 数据库文件与初始化脚本，都基于文件位置而不是 cwd
DB_PATH = os.path.join(EXAMPLES_DIR, "chat_bot.db")
INIT_SCRIPT = os.path.join(EXAMPLES_DIR, "fortune_init_data.py")


class QrFortune(Base):
    __tablename__ = "qr_fortune"

    id = Column(Integer, primary_key=True)
    fortune_summary = Column(String(255))
    lucky_star = Column(String(255))
    sign_text = Column(String(255))
    un_sign_text = Column(String(255))

    def __repr__(self):
        return (
            "QrFortune(id:{},fortune_summary:{},lucky_star:{},sign_text:{},un_sign_text:{})"
            .format(self.id, self.fortune_summary, self.lucky_star,
                    self.sign_text, self.un_sign_text)
        )


class QrFortuneLog(Base):
    __tablename__ = "qr_fortune_log"

    id = Column(Integer, primary_key=True)
    fortune_summary = Column(String(255))
    lucky_star = Column(String(255))
    sign_text = Column(String(255))
    un_sign_text = Column(String(255))
    user_id = Column(String(255))
    extract_time = Column(Date)

    def __repr__(self):
        return (
            "QrFortuneLog(id:{},user_id:{},fortune_summary:{})"
            .format(self.id, self.user_id, self.fortune_summary)
        )


class SqliteSqlalchemy(object):
    """SQLite 连接工厂。"""

    def __init__(self):
        # Windows 路径要转成正斜杠，四斜杠开头表示绝对路径
        url = "sqlite:///" + DB_PATH.replace("\\", "/")
        engine = create_engine(url, echo=False)
        self.session = sessionmaker(bind=engine)()


# 查询表是否存在
selectInit = text(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='qr_fortune';"
)
# 随机取一条运势
selectFortune = text("select * from qr_fortune order by random() limit 1")
# 查今天是否已经抽过（本地时区，不是 UTC）
selectFortuneLog = text(
    "select * from qr_fortune_log "
    "where user_id = :member_openid and extract_time = date('now','localtime')"
)
# 写入抽取日志
insertFortuneLog = text(
    "insert into qr_fortune_log "
    "(fortune_summary, lucky_star, sign_text, un_sign_text, user_id, extract_time) "
    "values (:fortune_summary, :lucky_star, :sign_text, :un_sign_text, "
    ":member_openid, date('now','localtime'))"
)


def _child_env():
    """初始化脚本也强制 UTF-8，避免中文写入数据库时乱码。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _format_fortune(row):
    return (
        "\n" + "您的今日运势为：" + "\n" +
        row.fortune_summary + "\n" +
        row.lucky_star + "\n" +
        "签文：" + row.sign_text + "\n" +
        "————————————————————" + "\n" +
        "解签：" + row.un_sign_text
    )


def get_today_fortune(member_openid):
    """返回该用户今天的运势文本（同一天重复调用返回同一条）。"""
    if not str(member_openid or "").strip():
        raise ValueError("member_openid 不能为空")

    result = is_get_fortune_log(member_openid)
    if result is not None:
        return _format_fortune(result)

    result = get_fortune()

    log = QrFortuneLog()
    log.fortune_summary = result.fortune_summary
    log.lucky_star = result.lucky_star
    log.sign_text = result.sign_text
    log.un_sign_text = result.un_sign_text
    log.user_id = member_openid
    insert_fortune_log(log)
    return _format_fortune(result)


def is_get_fortune_log(member_openid):
    """查询今天是否已抽过；有记录返回该行，否则返回 None。"""
    session = SqliteSqlalchemy().session
    try:
        return session.execute(
            selectFortuneLog, {"member_openid": member_openid}
        ).fetchone()
    finally:
        session.close()


def get_fortune():
    """随机取一条运势；表为空时先跑一次初始化脚本再取。"""
    session = SqliteSqlalchemy().session
    try:
        row = session.execute(selectFortune).fetchone()
    finally:
        session.close()

    if row is None:
        # 表存在但是空的（或者压根没建表），初始化后重试一次
        if execute_init_file():
            session = SqliteSqlalchemy().session
            try:
                row = session.execute(selectFortune).fetchone()
            finally:
                session.close()

    if row is None:
        raise RuntimeError(
            "运势数据表为空，且自动初始化失败。请手动运行：python fortune_init_data.py"
        )
    return row


def insert_fortune_log(log):
    """写入一条抽取记录。"""
    session = SqliteSqlalchemy().session
    try:
        session.execute(
            insertFortuneLog,
            {
                "fortune_summary": log.fortune_summary,
                "lucky_star": log.lucky_star,
                "sign_text": log.sign_text,
                "un_sign_text": log.un_sign_text,
                "member_openid": log.user_id,
            },
        )
        session.commit()
    finally:
        session.close()
    return ""


def database_initialized():
    """检查并（必要时）初始化数据库，返回表是否已就绪。"""
    session = SqliteSqlalchemy().session
    try:
        exists = session.execute(selectInit).fetchone()
    finally:
        session.close()

    if exists:
        print("表已创建。")
        return True

    print("表未创建。")
    execute_init_file()
    return False


def execute_init_file():
    """执行 fortune_init_data.py 初始化数据库，返回是否成功。"""
    if not os.path.isfile(INIT_SCRIPT):
        print("找不到初始化脚本：%s" % INIT_SCRIPT)
        return False

    try:
        subprocess.run(
            [sys.executable, INIT_SCRIPT],
            check=True,
            cwd=EXAMPLES_DIR,
            env=_child_env(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print("执行初始化文件时出错: %s" % exc)
        return False

    print("初始化文件已成功执行。")
    return True


if __name__ == "__main__":
    database_initialized()
