"""
manualDebug.py —— 带调试功能的 GUI 启动器（轻量化：只注入调试方法，其余全部复用 main）。

用法：
    .venv/Scripts/python.exe tools/manualDebug.py

通过本脚本启动的 GUI 才带测试键位与功能；直接 `python main.py` 启动的是纯净版（无这些）。

注入内容：
- 调试热键：F2 单车送车测试 / F4 单卡识别 / F5 大范围识别 / F6 整屏截图 / F7 诊断打包
- 日志落盘到 debug/gui_log.txt（main 仅在 debug_mode 时落盘）
- gift_current_car 的逐步序列存图（main 仅在 debug_mode 时存）
- 「送车测试」按钮（ui_layout 检测到本类的 start_gift_test 才创建）
- F7 诊断模式：打包窗口信息/校准/最近日志/整屏截图到 debug/diagnostics/<时间>/（借鉴上游诊断模式）
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


class FH_DebugBot(FH_UltimateBot):
    """调试版主程序：开启 debug_mode，注入测试方法与热键。"""

    def __init__(self):
        # 必须在 super().__init__() 之前置位：父类 __init__ 会 setup_ui + start_hotkey_listener，
        # 让 log 落盘、序列存图、送车测试按钮、调试热键都在 debug 模式下生效。
        self.debug_mode = True
        super().__init__()
        self.log("====== manualDebug 调试版已启动（F2送车测试 F4单卡识别 F5大范围 F6截图 F7诊断）======")

    # ---- 调试热键分发（被父类 start_hotkey_listener 的 on_press 调用）----
    def on_debug_hotkey(self, k):
        if k == keyboard.Key.f2:
            self.gift_one_card_test()
        elif k == keyboard.Key.f4:
            self.recognize_current_card()
        elif k == keyboard.Key.f5:
            self.recognize_largerange()
        elif k == keyboard.Key.f6:
            self.capture_full_debug()
        elif k == keyboard.Key.f7:
            self.dump_diagnostics()

    # ========================================================================
    # --- 以下为从 main.py 抽离出来的调试方法（只注入，逻辑不变）---
    # ========================================================================
    def gift_load_yolo(self):
        """加载 YOLO 模型（无视 ai_assist 开关，调试/识别用），失败返回 None。"""
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

    def gift_ai_counts(self, region, model):
        """在 region 上跑 YOLO，返回 (counts{new,b600,car}, 最大new置信度) 或 None。"""
        if model is None:
            return None
        try:
            bgr = self.capture_region(region)
            res = model.predict(source=bgr, imgsz=int(self.config.get("ai_imgsz", 960)),
                                conf=0.10, device=self.resolve_ai_device(), verbose=False)[0]
            counts = {"new": 0, "b600": 0, "car": 0}
            mx = 0.0
            if res.boxes is not None:
                for item in res.boxes:
                    b = self.yolo_box_to_dict(item, conf_threshold=0.0)
                    if b and b["name"] in counts:
                        counts[b["name"]] += 1
                        if b["name"] == "new":
                            mx = max(mx, b["conf"])
            return counts, mx
        except Exception as e:
            self.log(f"[识别] AI 推理异常: {e}")
            return None

    def recognize_current_card(self):
        """F4：单张识别当前选中卡（模板全新 + 目标车款 + AI），输出日志并存图。只读不动作。
        送车/专精选车界面通用——导航到任一界面按 F4 即可看当前选中卡的识别情况。"""
        def work():
            # 关键：识别函数（selected_card_has_new_tag / find_image_gray）会在
            # not is_running 时直接短路返回，所以 F4 期间临时置 True，结束恢复。
            prev_running = self.is_running
            self.is_running = True
            try:
                # F4 是全局热键，GUI 可能在前面遮挡游戏（整屏截图会抓进来）。
                # 先把 GUI 压到最底再聚焦游戏，确保截到的是干净的游戏画面。
                self.ui_call(self.lower)
                time.sleep(0.3)
                self.check_and_focus_game()
                time.sleep(0.3)
                region = self.find_selected_card_region()
                hl = "高亮" if region is not None else "回退固定框"
                if region is None:
                    region = self.selected_card_region()
                debug_dir = os.path.join(get_app_dir(), "debug", "gift_test")
                stamp = time.strftime("%H%M%S")
                fname = f"f4_{stamp}.png"
                self.write_debug_image(os.path.join(debug_dir, fname), self.capture_region(region))
                tag = self.selected_card_has_new_tag()
                is_target = self.selected_car_is_target()
                pconf = self.gift_panel_conf()
                ai = self.gift_ai_counts(region, self.gift_load_yolo())
                ai_str = "AI=跳过"
                if ai is not None:
                    c, mx = ai
                    ai_str = f"AI[new={c['new']} b600={c['b600']} car={c['car']} newconf={mx:.2f}]"
                self.log(f"[F4] ({hl}) 全新={tag} 目标车={is_target}(panel={pconf:.2f}) "
                         f"{ai_str} -> 已存 debug/gift_test/{fname}")
            except Exception as e:
                self.log(f"[F4] 识别异常: {e}")
            finally:
                self.is_running = prev_running
                self.ui_call(self.lift)   # 恢复 GUI 到前面，方便看日志
        threading.Thread(target=work, daemon=True).start()

    def gift_one_card_test(self):
        """F2：单车送车测试——对当前选中卡走真实送车决策：
        全新标记→跳过不送；非目标车→跳过不送；否则真实送出（gift_current_car）。
        手动选好车辆卡片后按 F2 触发。检测期间下沉 GUI 避免遮挡。"""
        # 同步守卫：on_press 串行，置位放线程外可挡住热键连发导致的双重送车
        if self.is_running:
            self.log("[F2] 已有任务运行中，忽略。")
            return
        self.is_running = True
        self.is_paused = False
        self.update_running_state("running")

        def work():
            try:
                self.ui_call(self.lower)
                time.sleep(0.3)
                if not self.check_and_focus_game():
                    self.log("[F2] 未能聚焦游戏。")
                    return
                time.sleep(0.3)
                tag = self.selected_card_has_new_tag()
                is_target = self.selected_car_is_target()
                pconf = self.gift_panel_conf()
                self.log(f"[F2] 当前选中卡：全新={tag} 目标车={is_target}(panel={pconf:.2f})")
                if tag:
                    self.log("[F2] 有全新标记 → 跳过，不送出。")
                    return
                if not is_target:
                    self.log("[F2] 非目标车款 → 跳过，不送出（防误送）。")
                    return
                self.log("[F2] 符合条件，执行真实送出...")
                result = self.gift_current_car()
                self.log(f"[F2] 送出结果：{result}")
            except Exception as e:
                self.log(f"[F2] 异常: {e}")
            finally:
                self.is_running = False
                self.is_paused = False
                self.update_running_state("idle")
                self.ui_call(self.lift)
        threading.Thread(target=work, daemon=True).start()

    def recognize_largerange(self):
        """F5：专精加点同款【大范围】识别——在整个选车界面扫描全新消耗车
        （find_new_consumable_car_strict），标注命中位置存图，只读不点击。
        用于测专精选车界面的识别（它不是按选中框、而是全屏找全新车）。"""
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
                # 用和正常流程同款的检测器：按 AI 设置走 AI(ai_only/ai_prefer)，否则模板
                pos = self.wait_for_new_consumable_car_strict(timeout=2.0, interval=0.2)
                pconf = self.gift_panel_conf()
                ai = self.gift_ai_counts(region, self.gift_load_yolo())
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
                self.log(f"[F5] 大范围全新车={'命中@'+str([int(v) for v in pos]) if pos else '未找到'} "
                         f"当前选中卡目标车panel={pconf:.2f}  {ai_str} -> debug/skill_test/{fname}")
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

    def start_gift_test(self):
        """送车干跑测试（F3 思路）：导航 + 重复筛选 + 逐卡检测全新标记并存检测区域图，
        全程绝不送车。用于实机校准导航/筛选/全新识别与 selected_card_region 区域。"""
        if self.is_running:
            self.log("已有任务正在运行，无法启动送车测试。")
            return
        self.is_running = True
        self.is_paused = False
        self.save_config()
        self.reset_run_stats()
        self.update_running_state("running")
        self.update_running_ui("送车测试", 0, 15)
        self.ui_call(self.lbl_runtime_loop.configure, text="测试模式")
        self.update_timer()
        self.log("====== 开始送车干跑测试（只检测/存图，绝不送车）======")

        # 复用类方法（F4 单张识别同款），避免重复
        def load_test_yolo():
            return self.gift_load_yolo()

        def ai_counts_on(region, model):
            return self.gift_ai_counts(region, model)

        def panel_conf():
            return self.gift_panel_conf()

        def runner():
            try:
                if not self.check_and_focus_game():
                    self.log("未能聚焦游戏窗口，测试结束。")
                    return
                if not self.navigate_to_giftbox():
                    self.log("[GiftTest] 导航或筛选失败，测试结束。")
                    return
                debug_dir = os.path.join(get_app_dir(), "debug", "gift_test")
                full = self.capture_region(self.regions["全界面"])
                self.write_debug_image(os.path.join(debug_dir, "00_fullscreen.png"), full)
                self.log(f"[GiftTest] 已存整屏 -> {debug_dir}\\00_fullscreen.png")

                # AI 基线：YOLO 在整屏礼物界面能识别到什么
                model = load_test_yolo()
                full_ai = ai_counts_on(self.regions["全界面"], model)
                if full_ai is not None:
                    c, mx = full_ai
                    self.log(f"[GiftTest] AI整屏基线: new={c['new']} b600={c['b600']} car={c['car']} "
                             f"最大new置信={mx:.2f}")

                # 先归位到第一辆车，再逐张向右遍历（动态高亮跟踪选中卡）
                self.go_to_list_start()
                time.sleep(0.5)

                N = 35
                self.update_running_ui("送车测试", 0, N)
                for i in range(N):
                    if not self.is_running:
                        break
                    self.check_pause()
                    # 动态找【当前选中卡】区域（高亮边框）；失败回退固定框
                    region = self.find_selected_card_region()
                    hl = "高亮" if region is not None else "回退固定框"
                    if region is None:
                        region = self.selected_card_region()
                    crop = self.capture_region(region)
                    self.write_debug_image(
                        os.path.join(debug_dir, f"card_{i + 1:02d}.png"), crop)
                    tpl_tag = self.selected_card_has_new_tag()   # 模板检测全新
                    is_target = self.selected_car_is_target()    # 左侧面板=目标车款?
                    p_conf = panel_conf()                        # 面板匹配置信(调阈值用)
                    ai = ai_counts_on(region, model)             # AI 检测
                    ai_str = "AI=跳过"
                    if ai is not None:
                        c, mx = ai
                        ai_str = f"AI[new={c['new']} b600={c['b600']} car={c['car']} newconf={mx:.2f}]"
                    self.update_running_ui("送车测试", i + 1, N)
                    self.log(f"[GiftTest] 卡#{i + 1}({hl}) 全新={tpl_tag} "
                             f"目标车={is_target}(panel={p_conf:.2f})  {ai_str} "
                             f"(已存 card_{i + 1:02d}.png)")
                    self.hw_press("right", delay=0.1)
                    time.sleep(0.4)
                self.log(f"[GiftTest] 干跑完成。检测图在 {debug_dir}")
            except Exception as e:
                self.log(f"送车测试异常: {e}")
            finally:
                self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

    # ========================================================================
    # --- F7 诊断模式（借鉴上游：打包一份排障材料，方便发出来分析）---
    # ========================================================================
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

                # 1) 整屏截图
                try:
                    self.write_debug_image(os.path.join(out_dir, "fullscreen.png"),
                                           self.capture_region(self.regions["全界面"]))
                except Exception as e:
                    self.log(f"[F7] 截图失败: {e}")

                # 2) summary.json：窗口信息 + 校准 + 配置摘要
                region = self.regions.get("全界面")
                summary = {
                    "timestamp": stamp,
                    "window_region_全界面": list(region) if region else None,
                    "game_hwnd": getattr(self, "game_hwnd", None),
                    "match_calibration": getattr(self, "match_calibration", None),
                    "config": {k: self.config.get(k) for k in (
                        "gift_max_count", "chk_gift", "wheelspin_mode", "wheelspin_max_count",
                        "wheelspin_owned_downs", "ai_only", "ai_assist", "smart_page",
                        "drive_keys", "global_loops")},
                }
                try:
                    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
                        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
                except Exception as e:
                    self.log(f"[F7] 写 summary.json 失败: {e}")

                # 3) 最近日志（从落盘的 gui_log.txt 取尾部）
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
