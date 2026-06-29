"""
3840 环境模拟：对三套模板(images根 / 1080P / 1440P)实测识图相关性。

真正调用 image_matcher 的缩放逻辑：
  - get_scales_to_try(fast_mode)  —— 用模拟的 3840 窗口 + 校准 preferred_scale=1.5
  - _scale_match_inputs(...)      —— 大模板缩整屏 / 小模板放大模板（与实机一致）
截图池：E:/FH6/screenshots/raw_3840 的原生 3840×2160（取前 N 张）。
每张模板取"对池中任意截图、任意缩放"的最高分；分别看：
  full = 全缩放梯(fast_mode=False) 能达到的最高分（"理论上能不能匹配到"）
  fast = 仅 top-8(fast_mode=True) 内能达到的最高分（"实机默认快路径找不找得到"）
fast 掉到阈值以下 = 实机在 3840 下有漏检风险。
"""
import os, sys, glob
import cv2, numpy as np

sys.path.insert(0, "E:/FH6/FH6")
import image_matcher
from image_matcher import cv2_imread

POOL_N = 10
THRESH = 0.85
SETS = [
    ("images根", "E:/FH6/FH6/images", True),    # True=排除 1080P/1440P 子目录
    ("1080P",    "E:/FH6/FH6/images/1080P", False),
    ("1440P",    "E:/FH6/FH6/images/1440P", False),
]


class Harness(image_matcher.ImageMatcherMixin):
    def __init__(self, w=3840):
        h = int(round(w * 2160 / 3840))
        self.regions = {"全界面": (0, 0, w, h)}
        self.match_calibration = {"preferred_scale": round(w / 2560.0, 3)}  # 3840 -> 1.5
        self._DOWNSCALE_SRC_AREA = 30000
        self.is_running = True

    def log(self, *a, **k):
        pass


def load_pool():
    pool = []
    for p in sorted(glob.glob("E:/FH6/screenshots/raw_3840/*.png"))[:POOL_N]:
        im = cv2_imread(p, cv2.IMREAD_GRAYSCALE)
        if im is not None and im.shape[1] >= 3800:
            pool.append(im)
    return pool


def best_score(h, tpl_raw, pool, scales):
    best = -1.0
    for scale in scales:
        screen0 = pool[0]
        sm0, tm, back = h._scale_match_inputs(screen0, tpl_raw, scale)
        th, tw = tm.shape[:2]
        if th < 5 or tw < 5:
            continue
        for screen in pool:
            sm, tm2, back2 = h._scale_match_inputs(screen, tpl_raw, scale)
            if tm2.shape[0] > sm.shape[0] or tm2.shape[1] > sm.shape[1]:
                continue
            v = float(cv2.matchTemplate(sm, tm2, cv2.TM_CCOEFF_NORMED).max())
            if v > best:
                best = v
    return best


def list_templates(root, exclude_sub):
    out = []
    for p in glob.glob(os.path.join(root, "**", "*.png"), recursive=True):
        rel = os.path.relpath(p, root).replace("\\", "/")
        if exclude_sub and (rel.startswith("1080P/") or rel.startswith("1440P/")):
            continue
        if "Screenshot 2026" in rel:
            continue
        out.append((rel, p))
    return sorted(out)


def main():
    h = Harness(3840)
    pool = load_pool()
    scales_full = h.get_scales_to_try(fast_mode=False)
    scales_fast = h.get_scales_to_try(fast_mode=True)
    lines = [f"=== 3840 模拟匹配 (池 {len(pool)} 张原生3840, 阈值 {THRESH}) ==="]
    lines.append(f"fast top-8 缩放梯: {scales_fast}")
    lines.append(f"full 全梯({len(scales_full)}): {scales_full}")
    summary = {}
    # 以 1440P 的模板清单为公共基准，三套对比同名模板
    common = [rel for rel, _ in list_templates("E:/FH6/FH6/images/1440P", False)]
    for name, root, excl in SETS:
        rows = []
        for rel, p in list_templates(root, excl):
            tpl = cv2_imread(p, cv2.IMREAD_GRAYSCALE)
            if tpl is None:
                continue
            bf = best_score(h, tpl, pool, scales_full)
            bq = best_score(h, tpl, pool, scales_fast)
            rows.append((rel, bf, bq))
        npass_full = sum(1 for _, bf, _ in rows if bf >= THRESH)
        npass_fast = sum(1 for _, _, bq in rows if bq >= THRESH)
        summary[name] = (len(rows), npass_full, npass_fast)
        lines.append(f"\n##### {name}  (共{len(rows)})  full命中{npass_full}  fast命中{npass_fast}")
        # 只打印"fast 掉下阈值"的（实机风险）+ 公共基准里的
        risky = [(rel, bf, bq) for rel, bf, bq in rows if bq < THRESH]
        lines.append(f"  -- fast 掉阈值(3840实机有风险) {len(risky)} 张:")
        for rel, bf, bq in sorted(risky, key=lambda x: x[2]):
            lines.append(f"     {rel:28s} full{bf:.3f} fast{bq:.3f}")
    lines.append("\n=== 汇总 (越靠 fast 命中越好) ===")
    for name in summary:
        n, pf, pq = summary[name]
        lines.append(f"  {name:8s}: 共{n}  full命中{pf}/{n}  fast命中{pq}/{n}")
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
