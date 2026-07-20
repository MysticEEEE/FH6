"""
manualDebug.py —— 带调试功能的 GUI 启动器（Mystic fork · 基于上游 v4.3）。

用法：
    python tools/manualDebug.py

通过本脚本启动的 GUI 才带测试键位；直接 `python main.py` 是纯净版（无调试热键）。

调试热键：
- F3 抽奖调试测试（连抽 N 次，每步存整屏截图 + skip/respin/owned/menu 命中日志）
- F4 AI 探针（对当前整屏跑 YOLO，打印 new/b600/car 计数 + 存图）
- F5 消耗车大范围识别（上游刷专精同款 wait_for_new_consumable_car，标注命中存图）
- F6 整屏截图 -> debug/screenshots
- F7 诊断打包（窗口/校准/配置/最近日志 -> debug/diagnostics）
- F8 停止    F9 开发者文本编辑器（上游）

说明：本 fork 与上游不同——原 F2/送车测试随送车功能弃用一并移除；F4/F5 由原
gift 识别改接上游的 YOLO / 消耗车识别 API。
"""
import os
import sys
import json
import time
import threading

import cv2
from pynput import keyboard

# 把仓库根目录加入 sys.path 以便导入 main（本文件在 tools/ 下）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from main import FH_UltimateBot          # noqa: E402
from app_resources import get_app_dir    # noqa: E402
import flow_wheelspin as fw              # noqa: E402


class FH_DebugBot(FH_UltimateBot):
    """调试版主程序：开启 debug_mode，注入测试热键。"""

    def __init__(self):
        # 必须在 super().__init__() 之前置位：父类 __init__ 会 setup_ui + start_hotkey_listener。
        self.debug_mode = True
        super().__init__()
        self.log("══════════ manualDebug 调试版已启动 ══════════")
        self.log("  F3 = 抽奖调试测试（连抽3次，每步存截图+识别日志）")
        self.log("  F4 = AI 探针（当前整屏跑 YOLO，打印计数+存图）")
        self.log("  F5 = 消耗车大范围识别（刷专精同款，全屏找新车）")
        self.log("  F6 = 整屏截图 -> debug/screenshots")
        self.log("  F7 = 诊断打包（窗口/校准/日志/截图 -> debug/diagnostics）")
        self.log("  F8 = 停止    F9 = 开发者文本编辑器")
        self.log("═══════════════════════════════════════════")

    # ---- 调试热键分发（被父类 start_hotkey_listener 的 on_press 调用）----
    def on_debug_hotkey(self, k):
        if k == keyboard.Key.f3:
            self.wheelspin_debug_test()
        elif k == keyboard.Key.f4:
            self.ai_probe_current()
        elif k == keyboard.Key.f5:
            self.recognize_consumable_largerange()
        elif k == keyboard.Key.f6:
            self.capture_full_debug()
        elif k == keyboard.Key.f7:
            self.dump_diagnostics()

    # ---- AI 辅助（调试/识别用，无视 ai_assist 开关）----
    def ai_load_yolo(self):
        """加载 YOLO 模型（先走正常入口；ai_assist 关时回退直接按路径加载），失败返回 None。"""
        m = self.get_yolo_car_select_model()
        if m is not None:
            return m
        try:
            path = self.resolve_ai_model_path()
            if not path:
                return None
            from ultralytics import YOLO
            return YOLO(path)
        except Exception as e:
            self.log(f"[识别] YOLO 加载失败: {e}")
            return None

    def ai_counts(self, region, model):
        """在 region 上跑 YOLO，返回 (counts{new,b600,car}, 最大 new 置信度) 或 None。"""
        if model is None:
            return None
        try:
            bgr = self.capture_region(region)
            res = model.predict(source=bgr, imgsz=int(self.config.get("ai_imgsz", 960)),
                                conf=0.10, device=self.resolve_ai_device(), verbose=False)[0]
            counts = {"new": 0, "b600": 0, "car": 0}
            # 上游模型类名是 new_tag/class_b600/target_car，兼容旧的 new/b600/car。
            name_map = {"new_tag": "new", "class_b600": "b600", "target_car": "car"}
            mx = 0.0
            if res.boxes is not None:
                for item in res.boxes:
                    b = self.yolo_box_to_dict(item, conf_threshold=0.0)
                    if not b:
                        continue
                    key = name_map.get(b["name"], b["name"])
                    if key in counts:
                        counts[key] += 1
                        if key == "new":
                            mx = max(mx, b["conf"])
            return counts, mx
        except Exception as e:
            self.log(f"[识别] AI 推理异常: {e}")
            return None

    def ai_probe_current(self):
        """F4：对当前整屏跑 YOLO，打印 new/b600/car 计数 + 存图。只读不动作。"""
        def work():
            try:
                self.ui_call(self.lower)
                time.sleep(0.3)
                self.check_and_focus_game()
                time.sleep(0.3)
                region = self.regions["全界面"]
                debug_dir = os.path.join(get_app_dir(), "debug", "ai_probe")
                stamp = time.strftime("%H%M%S")
                fname = f"f4_{stamp}.png"
                self.write_debug_image(os.path.join(debug_dir, fname), self.capture_region(region))
                ai = self.ai_counts(region, self.ai_load_yolo())
                if ai is None:
                    self.log(f"[F4] AI=不可用（模型未加载）-> 已存 debug/ai_probe/{fname}")
                else:
                    c, mx = ai
                    self.log(f"[F4] AI[new={c['new']} b600={c['b600']} car={c['car']} newconf={mx:.2f}] "
                             f"-> 已存 debug/ai_probe/{fname}")
            except Exception as e:
                self.log(f"[F4] 识别异常: {e}")
            finally:
                self.ui_call(self.lift)
        threading.Thread(target=work, daemon=True).start()

    def recognize_consumable_largerange(self):
        """F5：上游刷专精同款【大范围】识别——全屏找新消耗车（wait_for_new_consumable_car），
        标注命中位置存图，只读不点击。"""
        def work():
            prev_running = self.is_running
            self.is_running = True
            try:
                self.ui_call(self.lower)
                time.sleep(0.3)
                self.check_and_focus_game()
                time.sleep(0.3)
                region = self.regions["全界面"]
                full = self.capture_region(region)
                # 用和上游刷专精同款的检测器（按 ai 设置走 AI 或模板）
                pos = self.wait_for_new_consumable_car(timeout=2.0, interval=0.2)
                ai = self.ai_counts(region, self.ai_load_yolo())
                annotated = full.copy()
                if pos:
                    px, py = int(pos[0] - region[0]), int(pos[1] - region[1])
                    cv2.circle(annotated, (px, py), 45, (0, 0, 255), 5)
                debug_dir = os.path.join(get_app_dir(), "debug", "skill_test")
                stamp = time.strftime("%H%M%S")
                fname = f"f5_{stamp}.png"
                self.write_debug_image(os.path.join(debug_dir, fname), annotated)
                ai_str = "AI=跳过"
                if ai is not None:
                    c, mx = ai
                    ai_str = f"AI[new={c['new']} b600={c['b600']} car={c['car']} newconf={mx:.2f}]"
                self.log(f"[F5] 大范围新消耗车={'命中@' + str([int(v) for v in pos]) if pos else '未找到'} "
                         f"{ai_str} -> debug/skill_test/{fname}")
            except Exception as e:
                self.log(f"[F5] 识别异常: {e}")
            finally:
                self.is_running = prev_running
                self.ui_call(self.lift)
        threading.Thread(target=work, daemon=True).start()

    def capture_full_debug(self):
        """F6：存当前游戏完整截图到 debug/screenshots。"""
        def work():
            try:
                self.check_and_focus_game()
                time.sleep(0.2)
                img = self.capture_region(self.regions["全界面"])
                debug_dir = os.path.join(get_app_dir(), "debug", "screenshots")
                stamp = time.strftime("%Y%m%d_%H%M%S")
                path = os.path.join(debug_dir, f"full_{stamp}.png")
                self.write_debug_image(path, img)
                self.log(f"[F6] 已存完整截图 -> {path}")
            except Exception as e:
                self.log(f"[F6] 截图异常: {e}")
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # F3 抽奖调试测试（连抽 N 次，每步操作/识别都存截图+日志）
    # 调用真实 flow_wheelspin 模块函数，与实际抽奖流程完全一致。
    # ------------------------------------------------------------------
    def wheelspin_debug_test(self, spins_target=3):
        """F3：用当前抽奖模式连抽 spins_target 次，每一步（跳过/结果/领取/已拥有/出售）
        都存整屏截图 + 打印各模板(skip/respin/owned/menu)命中情况到 debug/wheelspin_seq/<时间>/。"""
        if self.is_running:
            self.log("[F3] 已有任务运行中，忽略。")
            return
        self.is_running = True
        self.is_paused = False
        self.update_running_state("running")

        def work():
            stamp = time.strftime("%H%M%S")
            seq = os.path.join(get_app_dir(), "debug", "wheelspin_seq", stamp)
            step = [0]

            def snap(tag):
                step[0] += 1
                try:
                    self.write_debug_image(os.path.join(seq, f"{step[0]:03d}_{tag}.png"),
                                           self.capture_region(self.regions["全界面"]))
                except Exception:
                    pass
                self.log(f"[F3] {step[0]:03d} {tag}")

            def detect(label):
                reg = self.regions["全界面"]
                prompt = fw._wheelspin_prompt_region(self)   # skip/respin 只在左下角
                r = self.find_image_gray("wheelspin/respin.png", region=prompt, threshold=0.7, fast_mode=True)
                s = self.find_image_gray("wheelspin/skip.png", region=prompt, threshold=0.7, fast_mode=True)
                o = self.find_image_gray("wheelspin/owned.png", region=reg, threshold=0.7, fast_mode=True)
                m = fw.is_wheelspin_finished(self)
                self.log(f"[F3] 识别({label}): 结果={'有' if r else '无'} 跳过={'有' if s else '无'} "
                         f"已拥有={'有' if o else '无'} 菜单={'有' if m else '无'}")
                return r, s, o, m

            try:
                self.ui_call(self.lower)
                time.sleep(0.3)
                if not self.check_and_focus_game():
                    self.log("[F3] 未能聚焦游戏。")
                    return
                time.sleep(0.3)
                snap("00_start")
                self.log(f"[F3] 模式={self.config.get('wheelspin_mode', '抽奖')}，目标 {spins_target} 抽。导航进入...")
                if not fw.navigate_to_wheelspin(self):
                    self.log("[F3] 导航失败，结束。")
                    return
                snap("01_entered_spin1_triggered")
                self._wheelspin_respin_pos = None

                for n in range(1, spins_target + 1):
                    if not self.is_running:
                        break
                    self.log(f"[F3] ===== 第 {n}/{spins_target} 抽 =====")
                    detect(f"spin{n}_before_advance")
                    snap(f"spin{n}_before_advance")
                    ready = fw.wheelspin_advance_to_result(self)
                    snap(f"spin{n}_after_advance")
                    if not self.is_running:
                        break
                    if not ready:
                        self.log(f"[F3] 第{n}抽：未到结果界面（可能已退回菜单），停止。")
                        break
                    self.log(f"[F3] 第{n}抽：结果界面就绪。")

                    if n >= spins_target:
                        self.log(f"[F3] 第{n}抽=最后一抽 → 按 ESC 仅领取不再抽。")
                        self.hw_press("esc")
                        time.sleep(1.2)
                        snap(f"spin{n}_esc_collected")
                        handled = fw.handle_owned_car_dialog(self)
                        snap(f"spin{n}_final_owned")
                        self.log(f"[F3] 第{n}抽：领取后出售 {handled} 辆重复车。")
                    else:
                        self.log(f"[F3] 第{n}抽：点击「领取并再抽」（触发下一抽）。")
                        fw.collect_and_respin(self)
                        snap(f"spin{n}_after_collect")

                snap("99_end")
                self.log(f"[F3] 抽奖调试测试结束。截图在 debug/wheelspin_seq/{stamp}/")
            except Exception as e:
                self.log(f"[F3] 异常: {e}")
            finally:
                self.is_running = False
                self.is_paused = False
                self.update_running_state("idle")
                self.ui_call(self.lift)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # F7 诊断打包（借鉴上游诊断模式：打包一份排障材料）
    # ------------------------------------------------------------------
    def dump_diagnostics(self):
        """F7：打包一份诊断材料到 debug/diagnostics/<时间>/：
        summary.json(窗口信息+自适应校准+配置摘要) + fullscreen.png(整屏) + recent_log.txt(最近日志)。"""
        def work():
            try:
                self.check_and_focus_game()
                time.sleep(0.2)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                out_dir = os.path.join(get_app_dir(), "debug", "diagnostics", stamp)
                os.makedirs(out_dir, exist_ok=True)

                try:
                    self.write_debug_image(os.path.join(out_dir, "fullscreen.png"),
                                           self.capture_region(self.regions["全界面"]))
                except Exception as e:
                    self.log(f"[F7] 截图失败: {e}")

                region = self.regions.get("全界面")
                summary = {
                    "timestamp": stamp,
                    "window_region_全界面": list(region) if region else None,
                    "game_hwnd": getattr(self, "game_hwnd", None),
                    "match_calibration": getattr(self, "match_calibration", None),
                    "config": {k: self.config.get(k) for k in (
                        "wheelspin_mode", "wheelspin_max_count", "wheelspin_owned_downs",
                        "ai_only", "ai_assist", "smart_page", "drive_keys",
                        "global_loops", "share_code", "buy_cj_vehicle")},
                }
                try:
                    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
                        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
                except Exception as e:
                    self.log(f"[F7] 写 summary.json 失败: {e}")

                try:
                    log_path = os.path.join(get_app_dir(), "debug", "gui_log.txt")
                    if os.path.exists(log_path):
                        with open(log_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()[-400:]
                        with open(os.path.join(out_dir, "recent_log.txt"), "w", encoding="utf-8") as f:
                            f.writelines(lines)
                except Exception as e:
                    self.log(f"[F7] 收集日志失败: {e}")

                self.log(f"[F7] 诊断已打包 -> debug/diagnostics/{stamp}/（summary.json + fullscreen.png + recent_log.txt）")
            except Exception as e:
                self.log(f"[F7] 诊断异常: {e}")
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    app = FH_DebugBot()
    app.mainloop()
