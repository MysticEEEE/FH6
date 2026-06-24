# tools/verify_template.py
"""对静态截图跑模板匹配，验证模板能否命中（多尺度，2560 基准）。
用法: python tools/verify_template.py images/giftbox/entry.png screenshots/02_礼物箱入口_车辆页.png 0.7
"""
import sys
import numpy as np
import cv2


def imread_u(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def main():
    tpl_path, scene_path = sys.argv[1], sys.argv[2]
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.7
    tpl = imread_u(tpl_path)
    scene = imread_u(scene_path)
    if tpl is None or scene is None:
        print("ERROR: 读图失败"); return 2
    tg = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    sg = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)

    best = (-1.0, None, None)
    for scale in [round(0.5 + 0.05 * i, 2) for i in range(25)]:  # 0.50 .. 1.70
        h, w = int(tg.shape[0] * scale), int(tg.shape[1] * scale)
        if h < 8 or w < 8 or h > sg.shape[0] or w > sg.shape[1]:
            continue
        t = cv2.resize(tg, (w, h), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(sg, t, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv > best[0]:
            best = (maxv, maxloc, scale)
    conf, loc, scale = best
    print(f"best conf={conf:.3f} scale={scale} loc={loc} (threshold={threshold})")
    if conf >= threshold:
        print("RESULT: 命中 ✓"); return 0
    print("RESULT: 未命中 ✗ —— 重新裁框或降阈值"); return 1


if __name__ == "__main__":
    sys.exit(main())
