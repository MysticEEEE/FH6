"""
manualDebug.py —— 带调试功能的 GUI 启动器（Mystic fork · deYangar 架构版）。

用法：
    python manualDebug.py

通过本脚本启动的 GUI 才带测试键位；直接 `python main.py` 是纯净版（无调试热键）。
deYangar 后台运行（PrintWindow 截图，游戏无需前台），故调试期间无需下沉 GUI。
deYangar 已占用 F3(测试找图)/F8(停止)/F9(暂停)，本调试键用 F4-F7：

- F4 抽奖调试测试（连抽 3 次，每步存整屏截图 + skip/respin/owned/menu 命中日志）
- F5 OCR 探针（对当前整屏底部/全屏跑 OCR，打印识别到的文字）
- F6 整屏截图 -> debug/screenshots
- F7 诊断打包（窗口/配置/整屏截图 -> debug/diagnostics）
"""
import os
import json
import time
import threading

import cv2
from pynput import keyboard

from main import FH_UltimateBot   # noqa: E402
from config import APP_DIR        # noqa: E402


class FH_DebugBot(FH_UltimateBot):
    """调试版主程序：注入 F4-F7 测试热键（不覆盖 deYangar 的 F3/F8/F9）。"""

    def __init__(self):
        super().__init__()
        self.log("══════════ manualDebug 调试版已启动 ══════════")
        self.log("  F4 = 抽奖调试测试（连抽3次，每步存截图+识别日志）")
        self.log("  F5 = OCR 探针（当前整屏跑 OCR，打印识别文字）")
        self.log("  F6 = 整屏截图 -> debug/screenshots")
        self.log("  F7 = 诊断打包（窗口/配置/截图 -> debug/diagnostics）")
        self.log("  F3 = 测试找图    F8 = 停止    F9 = 暂停/恢复")
        self.log("═══════════════════════════════════════════")

    def on_debug_hotkey(self, k):
        if k == keyboard.Key.f4:
            self.wheelspin_debug_test()
        elif k == keyboard.Key.f5:
            self.ocr_probe_current()
        elif k == keyboard.Key.f6:
            self.capture_full_debug()
        elif k == keyboard.Key.f7:
            self.dump_diagnostics()

    def _save_png(self, subdir, name, img):
        try:
            d = os.path.join(APP_DIR, "debug", subdir)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, name)
            cv2.imwrite(path, img)
            return path
        except Exception as e:
            self.log(f"[Debug] 存图失败: {e}")
            return None

    # F4：抽奖调试测试（调真实 WheelspinMixin 方法，与实际抽奖流程一致）
    def wheelspin_debug_test(self, spins_target=3):
        if self.is_running:
            self.log("[F4] 已有任务运行中，忽略。")
            return
        self.is_running = True
        self.is_paused = False
        self.update_running_state("running")

        def work():
            stamp = time.strftime("%H%M%S")
            step = [0]

            def snap(tag):
                step[0] += 1
                img = self.capture_region(self.regions["全界面"])
                if img is not None:
                    self._save_png(os.path.join("wheelspin_seq", stamp), f"{step[0]:03d}_{tag}.png", img)
                self.log(f"[F4] {step[0]:03d} {tag}")

            def detect(label):
                prompt = self._wheelspin_prompt_region()
                r = self.find_image_gray("ws_respin.png", region=prompt, threshold=0.7, fast_mode=True)
                s = self.find_image_gray("ws_skip.png", region=prompt, threshold=0.7, fast_mode=True)
                o = self.find_image_gray("ws_owned.png", region=self.regions["全界面"], threshold=0.7, fast_mode=True)
                m = self.is_wheelspin_finished()
                self.log(f"[F4] 识别({label}): 结果={'有' if r else '无'} 跳过={'有' if s else '无'} "
                         f"已拥有={'有' if o else '无'} 菜单={'有' if m else '无'}")

            try:
                if not self.check_and_focus_game():
                    self.log("[F4] 未能聚焦游戏。")
                    return
                snap("00_start")
                self.log(f"[F4] 模式={self.config.get('wheelspin_mode', '抽奖')}，目标 {spins_target} 抽。导航进入...")
                if not self.navigate_to_wheelspin():
                    self.log("[F4] 导航失败，结束。")
                    return
                snap("01_entered_spin1_triggered")
                self._wheelspin_respin_pos = None
                for n in range(1, spins_target + 1):
                    if not self.is_running:
                        break
                    self.log(f"[F4] ===== 第 {n}/{spins_target} 抽 =====")
                    detect(f"spin{n}_before")
                    snap(f"spin{n}_before")
                    ready = self.wheelspin_advance_to_result()
                    snap(f"spin{n}_after_advance")
                    if not self.is_running or not ready:
                        self.log(f"[F4] 第{n}抽未到结果界面（可能已退回菜单），停止。")
                        break
                    if n >= spins_target:
                        self.log(f"[F4] 第{n}抽=最后一抽 → ESC 仅领取。")
                        self.hw_press("esc")
                        time.sleep(1.2)
                        snap(f"spin{n}_esc")
                        handled = self.handle_owned_car_dialog()
                        self.log(f"[F4] 领取后处理 {handled} 个已拥有对话框。")
                    else:
                        self.collect_and_respin()
                        snap(f"spin{n}_after_collect")
                snap("99_end")
                self.log(f"[F4] 抽奖调试结束。截图在 debug/wheelspin_seq/{stamp}/")
            except Exception as e:
                self.log(f"[F4] 异常: {e}")
            finally:
                self.is_running = False
                self.is_paused = False
                self.update_running_state("idle")

        threading.Thread(target=work, daemon=True).start()

    # F5：OCR 探针 —— 对当前整屏底部+全屏跑 OCR，打印识别文字（调 deYangar OCR 引擎）
    def ocr_probe_current(self):
        def work():
            try:
                if not self.check_and_focus_game():
                    self.log("[F5] 未能聚焦游戏。")
                    return
                img = self.capture_region(self.regions["全界面"])
                if img is None:
                    self.log("[F5] 截图失败。")
                    return
                self._save_png("ocr_probe", f"f5_{time.strftime('%H%M%S')}.png", img)
                engine = self.get_ocr_engine()
                if engine is None:
                    self.log("[F5] OCR 引擎不可用。")
                    return
                bottom = engine.detect_text_in_region(
                    img, {"y_start": 0.9, "y_end": 1.0, "x_start": 0.0, "x_end": 1.0})
                full = engine.detect_text_in_region(img)
                self.log(f"[F5] OCR 底部条: {bottom!r}")
                self.log(f"[F5] OCR 全屏: {full!r}")
            except Exception as e:
                self.log(f"[F5] OCR 异常: {e}")
        threading.Thread(target=work, daemon=True).start()

    # F6：整屏截图
    def capture_full_debug(self):
        def work():
            try:
                if not self.check_and_focus_game():
                    self.log("[F6] 未能聚焦游戏。")
                    return
                img = self.capture_region(self.regions["全界面"])
                if img is not None:
                    path = self._save_png("screenshots", f"full_{time.strftime('%Y%m%d_%H%M%S')}.png", img)
                    self.log(f"[F6] 已存完整截图 -> {path}")
            except Exception as e:
                self.log(f"[F6] 截图异常: {e}")
        threading.Thread(target=work, daemon=True).start()

    # F7：诊断打包
    def dump_diagnostics(self):
        def work():
            try:
                self.check_and_focus_game()
                stamp = time.strftime("%Y%m%d_%H%M%S")
                out_dir = os.path.join(APP_DIR, "debug", "diagnostics", stamp)
                os.makedirs(out_dir, exist_ok=True)
                img = self.capture_region(self.regions["全界面"])
                if img is not None:
                    cv2.imwrite(os.path.join(out_dir, "fullscreen.png"), img)
                region = self.regions.get("全界面")
                summary = {
                    "timestamp": stamp,
                    "window_region_全界面": list(region) if region else None,
                    "game_hwnd": getattr(self, "game_hwnd", None),
                    "config": {k: self.config.get(k) for k in (
                        "wheelspin_mode", "wheelspin_max_count", "wheelspin_owned_downs",
                        "wheelspin_sell_dupes", "drive_keys", "current_scheme",
                        "use_directml", "share_code", "global_loops")},
                }
                with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
                self.log(f"[F7] 诊断已打包 -> debug/diagnostics/{stamp}/")
            except Exception as e:
                self.log(f"[F7] 诊断异常: {e}")
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    app = FH_DebugBot()
    app.mainloop()
