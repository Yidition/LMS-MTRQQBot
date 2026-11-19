# -*- coding: utf-8 -*-
import os
import json
import hashlib
import argparse
import time

import raqm_support  # noqa: F401  必须在 PIL 之前导入，负责注册 libraqm.dll
from opencc import OpenCC
from PIL import Image, ImageDraw, ImageFont

import logging_setup
from mtr_data import station_dwells, station_offsets

_log = logging_setup.get_logger("script.mtr_timetable")

cc_s2t = OpenCC('s2t')

def format_time(seconds):
    """将秒数格式化为 HH:MM:SS，修复浮点数报错"""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def generate_timetable(route_name, output_path, max_trains=15):
    started = time.perf_counter()
    LINK = 'http://localhost:1025'
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
    LOCAL_FILE_PATH = f'mtr-original-data-{link_hash}-mtr4-v4.json'
    DEP_PATH = f'mtr-route-departure-{link_hash}-mtr4-v4.json'
    BASE_PATH = 'mtr_pathfinder_data'

    if not os.path.exists(LOCAL_FILE_PATH) or not os.path.exists(DEP_PATH):
        print("ERROR: 找不到缓存数据文件，请先运行一次寻路生成数据。")
        return False

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)
    with open(DEP_PATH, encoding='utf-8') as f:
        dep_data = json.load(f)

    search_name_s = route_name.lower().strip()
    search_name_t = cc_s2t.convert(search_name_s)

    target_route = None
    for r_id, r_data in data['routes'].items():
        full_name = r_data['name'].lower()
        if search_name_s in full_name or search_name_t in full_name or route_name == r_id:
            target_route = r_data
            break

    if not target_route:
        print(f"ERROR: 找不到名为 {route_name} 的线路")
        return False

    route_id = target_route['id']
    if route_id not in dep_data:
        print(f"ERROR: 线路 {target_route['name']} 没有发车数据")
        return False

    stations = target_route['stations']
    if not stations:
        print(f"ERROR: 线路 {target_route.get('name', route_id)} 没有站点数据")
        return False

    durations = target_route.get('durations') or []
    # 停站时间挂在每个站点上，不是线路级字段（旧代码取错位置导致恒为 0）
    dwells = station_dwells(target_route, stations)
    # durations 单位是毫秒，station_offsets 内部会换算成秒
    offsets = station_offsets(stations, durations, dwells)

    # 站名要查 data['stations']：线路内的 stations[i]['name'] 只是序号（"1"、"2"…），
    # 直接用它会让整张表头全变成"站 1"。
    station_names = []
    for st in stations:
        st_id = st.get('id') if isinstance(st, dict) else None
        info = data.get('stations', {}).get(st_id) or {}
        name = info.get('name') or (st.get('name') if isinstance(st, dict) else None) or st_id or '?'
        station_names.append(str(name).split('|')[0].strip() or '?')

    departures = sorted(dep_data[route_id])
    if len(departures) > max_trains:
        departures = departures[:max_trains]

    _log.info(
        "匹配线路 name=%s id=%s 站点=%d 发车总数=%d 展示=%d",
        target_route.get('name'), route_id, len(stations),
        len(dep_data[route_id]), len(departures),
    )

    timetable_data = []
    for dep_time in departures:
        train_row = []
        for arr_off, dep_off in offsets:
            arr_time = dep_time + arr_off
            dep_time_station = dep_time + dep_off
            train_row.append((format_time(arr_time), format_time(dep_time_station)))
        timetable_data.append(train_row)

    font_path = os.path.join(BASE_PATH, 'fonts', 'NotoSansSC-Regular.ttf')
    font_title = ImageFont.truetype(font_path, 24)
    font_header = ImageFont.truetype(font_path, 18)
    font_text = ImageFont.truetype(font_path, 16)

    col_width = 130
    row_height = 40
    padding = 20
    
    img_width = padding * 2 + len(stations) * col_width
    img_height = padding * 2 + 60 + len(timetable_data) * row_height
    
    image = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(image)

    route_display_name = target_route['name'].replace('|', ' ')
    draw.text((padding, padding), f"线路时刻表: {route_display_name}", fill='black', font=font_title)
    
    y_header = padding + 50
    for i, full_name in enumerate(station_names):
        st_name = full_name if len(full_name) <= 6 else full_name[:5] + '…'
        if st_name.isdigit():
            st_name = "站 " + st_name
        x = padding + i * col_width
        draw.text((x, y_header), st_name, fill='black', font=font_header)
        draw.line([(x, y_header + 30), (x + col_width - 10, y_header + 30)], fill='black', width=2)

    y_data = y_header + 40
    for row_idx, row_data in enumerate(timetable_data):
        if row_idx % 2 == 0:
            draw.rectangle([(0, y_data - 5), (img_width, y_data + row_height - 5)], fill='#f0f0f0')
            
        for i, (arr, dep) in enumerate(row_data):
            x = padding + i * col_width
            if arr == dep:
                draw.text((x, y_data + 5), arr, fill='black', font=font_text)
            else:
                draw.text((x, y_data), f"{arr} 到", fill='gray', font=font_text)
                draw.text((x, y_data + 18), f"{dep} 发", fill='black', font=font_text)
        
        y_data += row_height

    draw.text((padding, y_data + 10), f"注：仅展示前 {len(timetable_data)} 趟列车", fill='gray', font=font_text)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    image.save(output_path)
    _log.info(
        "时刻表已生成 path=%s 画布=%dx%d 列车=%d 耗时=%.0fms",
        output_path, img_width, img_height, len(timetable_data),
        (time.perf_counter() - started) * 1000,
    )
    print(f"SUCCESS:{output_path}")
    return True

if __name__ == '__main__':
    logging_setup.setup_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("route", help="线路名称")
    parser.add_argument("--output", default="timetable.png", help="保存路径")
    parser.add_argument("--max-trains", type=int, default=15, help="最多显示几趟车")
    args = parser.parse_args()
    
    ok = generate_timetable(args.route, args.output, args.max_trains)
    # 失败时返回非 0，方便脚本/CI 判断（原来无论成功失败都退出 0）
    raise SystemExit(0 if ok else 1)
