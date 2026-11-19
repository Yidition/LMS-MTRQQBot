# -*- coding: utf-8 -*-
import os
import re
import json
import hashlib
import argparse
import time

import raqm_support  # noqa: F401  必须在 PIL 之前导入，负责注册 libraqm.dll / Must be imported before PIL; it registers libraqm.dll.
from opencc import OpenCC
from PIL import Image, ImageDraw, ImageFont

import logging_setup
from mtr_data import hex_color, station_dwells, station_offsets

_log = logging_setup.get_logger("script.mtr_diagram")

cc_s2t = OpenCC('s2t')

def format_time(seconds):
    seconds = int(seconds)
    h = int(seconds // 3600) % 24
    m = int((seconds % 3600) // 60)
    return f"{h:02d}:{m:02d}"

def generate_diagram(route_name, output_path, max_trains=20):
    started = time.perf_counter()
    LINK = 'http://localhost:1025'
    link_hash = hashlib.md5(LINK.encode('utf-8')).hexdigest()
    LOCAL_FILE_PATH = f'mtr-original-data-{link_hash}-mtr4-v4.json'
    DEP_PATH = f'mtr-route-departure-{link_hash}-mtr4-v4.json'
    BASE_PATH = 'mtr_pathfinder_data'

    if not os.path.exists(LOCAL_FILE_PATH) or not os.path.exists(DEP_PATH):
        print("ERROR: 找不到缓存数据文件。")
        return False

    with open(LOCAL_FILE_PATH, encoding='utf-8') as f:
        data = json.load(f)
    with open(DEP_PATH, encoding='utf-8') as f:
        dep_data = json.load(f)

    search_name = route_name.lower().strip()
    input_words = [w for w in re.split(r'[\s|/]+', search_name) if w]

    # 1. 匹配线路
    # 1. Match routes.
    matched_routes = []
    for r_id, r_data in data['routes'].items():
        r_name = r_data['name'].lower()
        if all(w in r_name for w in input_words) or r_id == route_name:
            matched_routes.append(r_data)

    if not matched_routes:
        direction_kws = ['上行', '下行', 'back', 'cw', 'ccw']
        filtered_words = [w for w in input_words if w not in direction_kws]
        if filtered_words:
            for r_id, r_data in data['routes'].items():
                r_name = r_data['name'].lower()
                if all(w in r_name for w in filtered_words):
                    matched_routes.append(r_data)

    if not matched_routes:
        print(f"ERROR: 找不到匹配 '{route_name}' 的线路")
        return False

    matched_routes = [r for r in matched_routes if r['id'] in dep_data]
    if not matched_routes:
        print(f"ERROR: 匹配的线路没有发车数据")
        return False

    # 2. 找基准线（停站最多的）
    # 2. Pick the base route, i.e. the one with the most stations.
    base_route = max(matched_routes, key=lambda r: len(r['stations']))
    
    y_axis_stations = []
    seen_stations = set()
    for st in base_route['stations']:
        st_id = st['id']
        if st_id not in seen_stations:
            real_name = data['stations'].get(st_id, {}).get('name', st_id).split('|')[0]
            y_axis_stations.append({'id': st_id, 'name': real_name})
            seen_stations.add(st_id)

    station_to_y = {st['id']: i for i, st in enumerate(y_axis_stations)}

    # 3. 处理站点：反向线路（CW / Back）要先把站序翻正再截断。
    #    反方向的站序是基准线的逆序，如果直接按"索引变小就截断"处理，
    #    会在第一站就判定为折返，只剩 1~2 站，画出来就是几根陡直的异常短线
    #    （实测 CW Back 只剩 1 站、CW / CW Rapid 只剩 2 站）。
    # 3. Process stations: for a reversed route (CW / Back), flip the station order back
    #    before truncating. A reversed route lists stations in reverse of the base route,
    #    so truncating as soon as "the index decreases" treats the first station as a
    #    reversal and keeps only 1-2 stations, drawing a few steep spurious short lines
    #    (measured: CW Back kept 1 station, CW / CW Rapid kept 2).
    def normalize_direction(route):
        stations = route['stations']
        durations = list(route.get('durations') or [])
        indices = [
            station_to_y[st['id']] for st in stations if st['id'] in station_to_y
        ]
        if len(indices) >= 2 and indices[0] > indices[1]:
            # 站点和时长一起倒序，保证 site i 与 i+1 之间的时长仍然对得上
            # Reverse stations and durations together so each segment duration still lines up.
            return list(reversed(stations)), list(reversed(durations))
        return stations, durations

    def get_clean_stations(route, stations=None):
        sts = stations if stations is not None else normalize_direction(route)[0]
        clean_sts = []
        last_idx = -1
        seen_idx = set()
        for st in sts:
            if st['id'] not in station_to_y:
                continue # 跳过不在基准线上的站 / Skip stations that are not on the base route.
            idx = station_to_y[st['id']]
            # 如果已经走过这个站，或者Y轴坐标变小了（说明开始折返/绕圈），就截断
            # Truncate once the station repeats or its Y index decreases, meaning a reversal
            # or a loop has begun.
            if idx in seen_idx or idx <= last_idx:
                break
            seen_idx.add(idx)
            clean_sts.append(st)
            last_idx = idx
        return clean_sts

    # 根据截断后的首尾站过滤反向线路
    # Filter out reversed routes by their trimmed first and last stations.
    base_stations, _ = normalize_direction(base_route)
    base_sts = get_clean_stations(base_route, base_stations)
    if not base_sts:
        print("ERROR: 基准线路数据异常")
        return False
    base_start = base_sts[0]['id']
    base_end = base_sts[-1]['id']

    final_routes = []
    for r in matched_routes:
        clean_sts = get_clean_stations(r)
        if not clean_sts:
            continue
        r_start = clean_sts[0]['id']
        r_end = clean_sts[-1]['id']
        
        if r_start == base_end and r_end == base_start:
            continue
        final_routes.append(r)

    if final_routes:
        matched_routes = final_routes

    # 4. 收集列车实例
    # 4. Collect train instances.
    normal_trains = []
    express_trains = []
    # 记录因为"有效站点不足 2 个"被跳过的线路数，用来区分失败原因
    # Count routes skipped for having fewer than 2 usable stations, to tell failures apart.
    degenerate_routes = 0
    
    for route in matched_routes:
        route_color = hex_color(route.get('color', 0))
        full_name = route['name'].lower()
        is_express = bool(re.search(r'rapid|fast|express|快速|快车|急行|特急', full_name))
        line_color = "#E53935" if is_express else route_color
        
        normalized, durations_all = normalize_direction(route)
        stations = get_clean_stations(route, normalized)
        # 少于 2 站画不出折线：以前会给这种车画出一个孤立点，图上是废线
        # Fewer than 2 stations cannot form a polyline; the old code drew a single isolated
        # point for such a train, which appeared as a stray line on the train diagram.
        if len(stations) < 2:
            degenerate_routes += 1
            continue
        # 时长跟着站点一起翻正，再截断到实际使用的站数
        # Flip the durations together with the stations, then trim them to the stations used.
        durations = durations_all[:len(stations) - 1]
        # 停站时间挂在每个站点上，不是线路级字段（旧代码取错位置导致恒为 0）
        # Dwell time is attached to each station, not to the route (the old code read it
        # from the wrong place, so it was always 0).
        dwells = station_dwells(route, stations)
        offsets = station_offsets(stations, durations, dwells)

        departures = sorted(dep_data[route['id']])
        for dep_time in departures:
            train_info = {
                'color': line_color,
                'is_express': is_express,
                'dep_time': dep_time,
                'offsets': offsets,
                'stations': stations,
                'arrival_time': dep_time + offsets[-1][1]
            }
            if is_express:
                express_trains.append(train_info)
            else:
                normal_trains.append(train_info)

    # 5. 智能抽取
    # 5. Smart sampling.
    normal_trains.sort(key=lambda x: x['dep_time'])
    express_trains.sort(key=lambda x: x['dep_time'])

    if not express_trains:
        all_train_instances = normal_trains[:max_trains]
    elif not normal_trains:
        all_train_instances = express_trains[:max_trains]
    else:
        half_max = max_trains // 2
        selected_normals = normal_trains[:half_max]
        selected_express = express_trains[:half_max]
        
        remain = max_trains - len(selected_normals) - len(selected_express)
        if remain > 0:
            if len(selected_normals) < half_max and len(express_trains) > half_max:
                selected_express.extend(express_trains[half_max : half_max + remain])
            elif len(selected_express) < half_max and len(normal_trains) > half_max:
                selected_normals.extend(normal_trains[half_max : half_max + remain])

        all_train_instances = selected_normals + selected_express
        all_train_instances.sort(key=lambda x: x['dep_time'])

    if not all_train_instances:
        # 区分"线路数据本身画不出图"和"没有发车时刻"，否则用户看到的报错会误导
        # Distinguish "the route data cannot be drawn" from "no departure times", otherwise
        # the error shown to users is misleading.
        if degenerate_routes:
            print("ERROR: 线路站序数据异常（有效站点不足 2 个），无法生成运行图")
        else:
            print("ERROR: 没有找到发车时间")
        return False

    # 6. 尺寸计算
    # 6. Size calculation.
    start_time = all_train_instances[0]['dep_time']
    end_time = max(t['arrival_time'] for t in all_train_instances)
    total_time = end_time - start_time
    if total_time < 60: 
        total_time = 60

    padding_left = 180
    padding_top = 60
    padding_right = 50
    padding_bottom = 50
    
    row_height = 45
    target_width = 2000
    x_scale = (target_width - padding_left - padding_right) / total_time
    
    img_width = int(padding_left + total_time * x_scale + padding_right)
    img_height = int(padding_top + len(y_axis_stations) * row_height + padding_bottom)

    image = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(image)

    font_path = os.path.join(BASE_PATH, 'fonts', 'NotoSansSC-Regular.ttf')
    font_title = ImageFont.truetype(font_path, 22)
    font_text = ImageFont.truetype(font_path, 16)

    draw.text((padding_left, 20), f"列车运行图: {route_name}", fill='black', font=font_title)

    for i, st in enumerate(y_axis_stations):
        y = padding_top + i * row_height
        draw.text((20, y - 10), st['name'][:12], fill='black', font=font_text)
        draw.line([(padding_left, y), (img_width - padding_right, y)], fill='#EEEEEE', width=1)

    if total_time <= 1800:
        time_step = 300
    elif total_time <= 3600:
        time_step = 600
    elif total_time <= 7200:
        time_step = 900
    else:
        time_step = 1800

    current_t = int((start_time // time_step) * time_step)
    while current_t <= end_time + time_step:
        if current_t >= start_time - 60:
            x = padding_left + (current_t - start_time) * x_scale
            draw.line([(x, padding_top - 10), (x, img_height - padding_bottom)], fill='#E0E0E0', width=1)
            draw.text((x - 20, img_height - padding_bottom + 10), format_time(current_t), fill='gray', font=font_text)
        current_t += time_step

    draw.line([(padding_left, padding_top - 10), (padding_left, img_height - padding_bottom)], fill='black', width=2)
    draw.line([(padding_left, padding_top - 10), (img_width - padding_right, padding_top - 10)], fill='black', width=2)

    # 7. 绘制折线
    # 7. Draw the polylines.
    label_positions = []   # 已经画过"普/快"标签的横坐标，用于避免重叠 / X coords of drawn "普/快" labels, to avoid overlap.
    for train in all_train_instances:
        line_color = train['color']
        line_width = 3 if train['is_express'] else 2
        dep_time = train['dep_time']
        points = []

        for i, (arr_off, dep_off) in enumerate(train['offsets']):
            st_id = train['stations'][i]['id']
            y = padding_top + station_to_y[st_id] * row_height
            x_arr = padding_left + (dep_time + arr_off - start_time) * x_scale
            x_dep = padding_left + (dep_time + dep_off - start_time) * x_scale
            points.append((x_arr, x_dep, y))

        for i in range(len(points) - 1):
            curr_x_arr, curr_x_dep, curr_y = points[i]
            next_x_arr, next_x_dep, next_y = points[i+1]

            if curr_x_dep > curr_x_arr:
                draw.line([(curr_x_arr, curr_y), (curr_x_dep, curr_y)], fill=line_color, width=line_width)
            
            draw.line([(curr_x_dep, curr_y), (next_x_arr, next_y)], fill=line_color, width=line_width)
            
            if i == 0:
                label = "快" if train['is_express'] else "普"
                # 发车时间接近的列车，标签会叠成一坨"普普普"，间距太近就跳过
                # Labels of trains departing at similar times pile up into "普普普", so skip
                # a label when it is too close to an existing one.
                if all(abs(curr_x_dep - x) >= 16 for x in label_positions):
                    draw.text((curr_x_dep + 2, curr_y - 20), label, fill=line_color, font=font_text)
                    label_positions.append(curr_x_dep)

        if len(points) > 0:
            last_x_arr, last_x_dep, last_y = points[-1]
            if last_x_dep > last_x_arr:
                draw.line([(last_x_arr, last_y), (last_x_dep, last_y)], fill=line_color, width=line_width)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    image.save(output_path)
    _log.info(
        "运行图已生成 path=%s 画布=%dx%d 基准线=%s 匹配线路=%d 列车=%d 耗时=%.0fms",
        output_path, img_width, img_height, base_route.get('name'),
        len(matched_routes), len(all_train_instances),
        (time.perf_counter() - started) * 1000,
    )
    print(f"SUCCESS:{output_path}")
    return True

if __name__ == '__main__':
    logging_setup.setup_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("route", help="线路名称及方向")
    parser.add_argument("--output", default="diagram.png", help="保存路径")
    parser.add_argument("--max-trains", type=int, default=20, help="总共显示多少趟车")
    args = parser.parse_args()
    
    ok = generate_diagram(args.route, args.output, args.max_trains)
    # 失败时返回非 0，方便脚本/CI 判断（原来无论成功失败都退出 0）
    # Return non-zero on failure so scripts/CI can detect it (previously it always exited 0).
    raise SystemExit(0 if ok else 1)
