"""
模板验证工具：拿一套模板去"当前游戏的 2560 截图池"里实测，确认每张能否匹配到真实画面，
并对比亮度，自动标出坏图（全黑/错裁/过时）。

用法：
    .venv/Scripts/python.exe tools/validate_templates.py [子目录]
    子目录默认 1440P；传 "" 验证 images/ 根；传 "1080P" 验证上游参照集。

判定：
    [BAD]  匹配分 < 0.80（在当前截图里找不到内容）或 亮度<35（疑似全黑）
    [WARN] 0.80~0.88（偏低，建议人工看）
    [OK]   >=0.88

截图池：E:/FH6/screenshots(含 2560/) + debug/snaps + debug/gift_seq + debug/wheelspin_seq，仅取宽 2520-2600。
为提速：先把池和模板按 ~0.32 缩小做粗匹配（验证只需判断"找不找得到"，不需精定位）。
"""
import cv2, numpy as np, os, glob, sys

ROOT = "E:/FH6/FH6"
SUB = sys.argv[1] if len(sys.argv) > 1 else "1440P"
TPL_DIR = os.path.join(ROOT, "images", SUB) if SUB else os.path.join(ROOT, "images")
ORIG_DIR = os.path.join(ROOT, "images")
COARSE = 0.32  # 池/模板粗缩比例（提速）


def imread_u(p, flag=cv2.IMREAD_GRAYSCALE):
    if not os.path.exists(p):
        return None
    return cv2.imdecode(np.fromfile(p, np.uint8), flag)


def brightness(p):
    im = imread_u(p, cv2.IMREAD_COLOR)
    return None if im is None else float(im.mean())


def build_pool():
    pats = [
        "E:/FH6/screenshots/*.png", "E:/FH6/screenshots/*.jpg",
        "E:/FH6/screenshots/2560/*.png", "E:/FH6/screenshots/2560/*.jpg",
        ROOT + "/debug/snaps/*.png", ROOT + "/debug/gift_seq/*.png",
        ROOT + "/debug/wheelspin_seq/*.png",
    ]
    pool = []
    for g in pats:
        for p in glob.glob(g):
            im = imread_u(p)
            if im is not None and 2520 <= im.shape[1] <= 2600:
                small = cv2.resize(im, None, fx=COARSE, fy=COARSE, interpolation=cv2.INTER_AREA)
                pool.append((os.path.basename(p), small))
    return pool


def best_match(tpl_gray, pool):
    """粗缩后多尺度匹配，返回 (最佳分, 来源截图)。"""
    best = (-1.0, "")
    for s in [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 2.0, 2.4]:
        eff = s * COARSE
        t = cv2.resize(tpl_gray, None, fx=eff, fy=eff, interpolation=cv2.INTER_AREA if eff < 1 else cv2.INTER_LINEAR)
        if t.shape[0] < 5 or t.shape[1] < 5:
            continue
        for name, pim in pool:
            if t.shape[0] <= pim.shape[0] and t.shape[1] <= pim.shape[1]:
                v = float(cv2.matchTemplate(pim, t, cv2.TM_CCOEFF_NORMED).max())
                if v > best[0]:
                    best = (v, name)
    return best


def main():
    pool = build_pool()
    tpls = sorted(glob.glob(os.path.join(TPL_DIR, "**", "*.png"), recursive=True))
    tpls = [p for p in tpls if "Screenshot 2026" not in p]
    out = []
    for tp in tpls:
        rel = os.path.relpath(tp, TPL_DIR).replace("\\", "/")
        g = imread_u(tp)
        if g is None:
            out.append((rel, "LOADFAIL", -1, 0, ""))
            continue
        sc, src = best_match(g, pool)
        b = brightness(tp)
        if sc < 0.80 or b < 35:
            st = "BAD"
        elif sc < 0.88:
            st = "WARN"
        else:
            st = "OK"
        out.append((rel, st, sc, b, src))
    order = {"BAD": 0, "WARN": 1, "LOADFAIL": 0, "OK": 2}
    lines = [f"=== 验证 images/{SUB or ''}  (池 {len(pool)} 张 2560 截图) ==="]
    for rel, st, sc, b, src in sorted(out, key=lambda x: (order.get(x[1], 9), -x[2])):
        lines.append(f"  [{st:4s}] {rel:30s} 匹配{sc:.3f} 亮度{b:.0f}  <-{src}")
    nbad = sum(1 for o in out if o[1] in ("BAD", "LOADFAIL"))
    nwarn = sum(1 for o in out if o[1] == "WARN")
    lines.append(f"--- 共 {len(out)}：BAD {nbad}  WARN {nwarn}  OK {len(out)-nbad-nwarn} ---")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
