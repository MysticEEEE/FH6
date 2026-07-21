"""自动抽奖流程（游戏内老虎机抽奖 / 超级抽奖）—— deYangar 架构版（mixin 方法）。

与 cj_logic 的技能点/车辆精通刷取不是同一功能——本模块是真正的游戏内转盘抽奖：
连续抽奖、抽到已拥有重复车按「卖出重复车」开关卖出或入库、跳过动画，直到退回
「我的地平线」菜单或达到次数上限。纯停止判断见 wheelspin_logic.py。

模板图（basename，平铺在 images/，get_img_path 只取 basename）：
ws_menu_anchor / ws_entry_super / ws_entry_wheelspin / ws_respin / ws_skip / ws_owned
"""

import time
import threading


class WheelspinMixin:
    def navigate_to_wheelspin(self):
        """enter_menu → pagedown 切到「我的地平线」标签页 → 点击「抽奖/超级抽奖」入口。
        用 ws_menu_anchor.png（「我的地平线」高亮标签）确认到位。成功返回 True。"""
        mode = self.config.get("wheelspin_mode", "抽奖")
        entry_tpl = ("ws_entry_super.png" if mode == "超级抽奖"
                     else "ws_entry_wheelspin.png")
        self.log(f"[Wheelspin] 准备进入主菜单...（模式：{mode}）")
        if not self.enter_menu():
            self.log("[Wheelspin] 进入主菜单失败。")
            return False

        # 从「剧情」标签向右移动到「我的地平线」标签（pagedown 每次右移一个标签）。
        self.log("[Wheelspin] 切换到「我的地平线」标签页...")
        self.check_pause()
        self.hw_press("pagedown", delay=0.15)
        time.sleep(0.6)
        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        # 识别驱动：确认「我的地平线」菜单锚点到位；未到位再右移一格重试（最多 4 次）。
        found = False
        for attempt in range(4):
            if not self.is_running:
                return False
            self.check_pause()
            if self.wait_for_image_gray(
                    "ws_menu_anchor.png", region=self.regions["全界面"],
                    threshold=0.7, timeout=3, interval=0.25, fast_mode=False):
                found = True
                break
            self.log(f"[Wheelspin] 未锚定到「我的地平线」，再右移一格重试...({attempt + 1}/4)")
            self.hw_press("pagedown", delay=0.15)
            time.sleep(0.8)
        if not found:
            self.log("[Wheelspin] 未能定位「我的地平线」菜单页。")
            self.capture_diagnostic_snapshot(
                "wheelspin_menu_fail", region=self.regions["全界面"],
                reason="未锚定「我的地平线」菜单")
            return False

        # 点击对应抽奖入口（用彩色匹配，借助底色区分青色超抽 / 绿色抽奖）。
        self.check_pause()
        pos_entry = self.wait_for_image(
            entry_tpl, region=self.regions["全界面"],
            threshold=0.72, timeout=6, interval=0.3, fast_mode=False)
        if not pos_entry:
            self.log(f"[Wheelspin] 未找到「{mode}」入口图块。")
            self.capture_diagnostic_snapshot(
                "wheelspin_entry_fail", region=self.regions["全界面"],
                reason=f"未找到「{mode}」入口")
            return False
        self.game_click(pos_entry)
        time.sleep(0.6)   # 入口已触发第1抽，尽快交给 advance_to_result 轮询，别错过首抽的「跳过」窗口
        self.log(f"[Wheelspin] 已点击「{mode}」入口，进入抽奖。")
        return True

    def is_wheelspin_finished(self):
        """是否已退回「我的地平线」菜单（确定性结束信号：次数用尽会自动返回菜单）。"""
        return self.find_image_gray(
            "ws_menu_anchor.png", region=self.regions["全界面"],
            threshold=0.7, fast_mode=False) is not None

    def _wheelspin_prompt_region(self):
        """抽奖左下角提示区——「Enter 跳过」/「Enter 领取并再抽」总在这一角。
        把 skip/respin 搜索限定到这里：搜索面积小→更快更跟手，过渡帧更易命中。"""
        x, y, w, h = self.regions["全界面"]
        return (x, y + int(h * 0.80), int(w * 0.45), int(h * 0.20))

    def wheelspin_advance_to_result(self, budget=22.0):
        """一抽触发后，统一【高频轮询(~0.12s)】推进到「结果界面就绪」。每帧（按优先级）：
          结果界面(respin，左下提示区) → 返回 True（最高优先，绝不再动作，那里点击/Enter=再抽）
          已拥有车辆(owned，全屏)      → 卖出/入库，继续
          跳过(skip，左下提示区)        → 点击（1s 冷却），逐个跳过动画
          退回菜单(menu)               → 返回 False（每 ~1s 查一次，避免拖慢轮询）"""
        downs = int(self.config.get("wheelspin_owned_downs", 2))
        sell_dupes = bool(self.config.get("wheelspin_sell_dupes", True))
        deadline = time.time() + budget
        last_click = 0.0
        last_menu_check = 0.0
        while time.time() < deadline:
            if not self.is_running:
                return False
            self.check_pause()
            prompt = self._wheelspin_prompt_region()
            # 1. 结果界面就绪 → 立刻返回
            if self.find_image_gray("ws_respin.png", region=prompt,
                                    threshold=0.7, fast_mode=True):
                return True
            # 2. 途中弹「已拥有车辆」→ 卖出 / 入库（仅确实检测到才按方向键，绝不盲按）
            if self.find_image_gray("ws_owned.png", region=self.regions["全界面"],
                                    threshold=0.7, fast_mode=True):
                if sell_dupes:
                    self.log("[Wheelspin] 检测到「已拥有车辆」→ 出售重复车。")
                    for _ in range(downs):
                        self.hw_press("down", delay=0.12)
                        time.sleep(0.2)
                else:
                    # 不卖车：上移到顶部项「添加至车库」（菜单顶部会 clamp），普通/超级抽奖都可靠入库
                    self.log("[Wheelspin] 检测到「已拥有车辆」→ 添加至车库（不卖车）。")
                    for _ in range(downs):
                        self.hw_press("up", delay=0.12)
                        time.sleep(0.2)
                self.hw_press("enter", delay=0.12)
                time.sleep(0.8)
                continue
            # 3. 转盘动画期：看到「跳过」就点（1s 冷却）
            if time.time() - last_click > 1.0:
                pos_skip = self.find_image_gray("ws_skip.png", region=prompt,
                                                threshold=0.7, fast_mode=True)
                if pos_skip:
                    self.game_click(pos_skip)
                    last_click = time.time()
                    self.log("[Wheelspin] 点击「跳过」加速动画。")
                    time.sleep(0.1)
                    continue
            # 4. 退回菜单（隔 ~1s 查一次，全屏匹配较慢，不必每帧）
            if time.time() - last_menu_check > 1.0:
                last_menu_check = time.time()
                if self.is_wheelspin_finished():
                    return False
            time.sleep(0.12)
        return self.find_image_gray("ws_respin.png", region=self._wheelspin_prompt_region(),
                                    threshold=0.7, fast_mode=True) is not None

    def collect_and_respin(self):
        """领取奖励并再抽：优先鼠标点击左下角「领取奖励并再次抽奖」按钮（首次定位后缓存坐标），
        避免连发 enter 在已拥有对话框出现时误触选项1。定位失败时仅在确认无对话框后回退按 enter。"""
        pos = getattr(self, "_wheelspin_respin_pos", None)
        if pos is None:
            pos = self.find_image_gray("ws_respin.png", region=self._wheelspin_prompt_region(),
                                       threshold=0.7, fast_mode=False)
            if pos:
                self._wheelspin_respin_pos = pos
        if pos:
            self.game_click(pos)
            time.sleep(1.0)
            return True
        # 回退：仅在确认当前【没有】已拥有对话框时才盲按 enter（防误加入库）
        if not self.find_image_gray("ws_owned.png", region=self.regions["全界面"],
                                    threshold=0.7, fast_mode=True):
            self.log("[Wheelspin] 未定位领取按钮，回退按 enter 领取。")
            self.hw_press("enter")
            time.sleep(1.0)
        return False

    def collect_only(self):
        """最后一抽：只领取、不再抽——按 ESC 领取奖励（不是 enter，enter 会再抽）。
        领取后正常直接回到「我的地平线」；若领取触发了「已拥有车辆」对话框，由调用方再出售。"""
        self.hw_press("esc")
        time.sleep(1.2)
        return True

    def handle_owned_car_dialog(self):
        """检测「已拥有车辆」对话框并卖出/入库重复车。超抽一次最多 3 车，可能连续弹多个对话框，
        故循环处理直到检测不到为止。返回处理过的对话框数量。

        安全闸门：仅在【确实检测到】对话框时才用方向键+enter，绝不盲按。
        卖车开关开：按 wheelspin_owned_downs 次「下」到「出售」卖出；
        关：按同样次数「上」到顶部「添加至车库」入库。"""
        downs = int(self.config.get("wheelspin_owned_downs", 2))
        sell_dupes = bool(self.config.get("wheelspin_sell_dupes", True))
        handled = 0
        for idx in range(4):  # 安全上限：最多连续处理 4 个对话框
            if not self.is_running:
                break
            self.check_pause()
            # 首个对话框给足时间出现（超抽较慢）；后续来得快，缩短等待降低无重复车时的空等
            timeout = 3.5 if idx == 0 else 1.5
            if not self.wait_for_image_gray(
                    "ws_owned.png", region=self.regions["全界面"],
                    threshold=0.7, timeout=timeout, interval=0.2, fast_mode=True):
                break
            if sell_dupes:
                self.log("[Wheelspin] 检测到「已拥有车辆」→ 选择「出售」卖出重复车。")
                for _ in range(downs):
                    self.hw_press("down", delay=0.12)
                    time.sleep(0.25)
            else:
                self.log("[Wheelspin] 检测到「已拥有车辆」→ 添加至车库（不卖车）。")
                for _ in range(downs):
                    self.hw_press("up", delay=0.12)
                    time.sleep(0.25)
            self.hw_press("enter", delay=0.12)
            time.sleep(1.0)
            handled += 1
        if handled:
            self.log(f"[Wheelspin] 已处理 {handled} 个「已拥有车辆」对话框。")
        return handled

    def logic_auto_wheelspin(self):
        """自动抽奖主流程：连续抽奖，抽到已拥有重复车按开关卖出/入库，直到退回菜单或达次数上限。"""
        try:
            max_count = int(self.config.get("wheelspin_max_count", 0))
        except Exception:
            max_count = 0

        if not self.navigate_to_wheelspin():
            return False

        self._wheelspin_respin_pos = None  # 「领取并再抽」按钮坐标缓存
        spins = 1                          # 点击入口本身已自动触发第 1 抽，计入
        no_result_streak = 0
        self.update_running_ui("自动抽奖", spins, max_count or 0)
        self.log(f"[Wheelspin] 入口已触发第 1 抽（上限={max_count or '不限'}）。")

        while self.is_running:
            self.check_pause()

            ready = self.wheelspin_advance_to_result()
            if not ready:
                if self.is_wheelspin_finished():
                    self.log("[Wheelspin] 已退回菜单，抽奖结束。")
                    break
                no_result_streak += 1
                if no_result_streak >= 3:
                    self.log("[Wheelspin] 连续多次未出现奖励结果界面，停止以防异常。")
                    break
                continue
            no_result_streak = 0

            # 达次数上限 → 最后一抽：ESC 仅领取不再抽；领取后仍可能弹「已拥有」→ 卖出/入库
            if max_count and spins >= max_count:
                self.log(f"[Wheelspin] 第 {spins} 抽为最后一抽 → 按 ESC 仅领取不再抽。")
                self.collect_only()
                self.handle_owned_car_dialog()
                self.log(f"[Wheelspin] 达到上限 {max_count}，停止。")
                break

            self.collect_and_respin()
            spins += 1
            self.update_running_ui("自动抽奖", spins, max_count or 0)
            self.log(f"[Wheelspin] 已触发第 {spins} 抽。")

        self.log(f"[Wheelspin] 抽奖流程结束，共抽 {spins} 次。")
        return True

    def start_wheelspin_pipeline(self):
        """GUI「自动抽奖」入口：独立的游戏内转盘抽奖流程（区别于 CJ 刷专精）。"""
        if self.is_running:
            self.log("已有任务正在运行，无法启动抽奖。")
            return
        self.is_running = True
        self.is_paused = False
        self.save_config()
        try:
            self.start_anti_cheat_heartbeat()
        except Exception:
            pass
        self.reset_run_stats()
        self.update_running_state("running")
        self.update_running_ui("自动抽奖", 0, 0)
        self.update_timer()
        mode = self.config.get("wheelspin_mode", "抽奖")
        self.log(f"====== 开始自动抽奖（模式：{mode}） ======")

        def runner():
            try:
                if not self.check_and_focus_game():
                    self.log("未能聚焦游戏窗口，抽奖结束。")
                    return
                self.logic_auto_wheelspin()
            except Exception as e:
                self.log(f"抽奖流程异常: {e}")
            finally:
                self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()
