# FH6 自动化 · 项目状态与交接文档

> 用途：项目级"记忆"。换电脑/换 Claude 会话时先读本文，即可快速接手继续开发与调试。
> 最后更新：2026-06-28。分支 `feature/auto-gift-cars`，远程 `mystic`(github.com/MysticEEEE/FH6，fork 自 `origin`=AxeroYF/FH6)。
> 配套文档：`docs/CODEBASE_MAP.md`(原始代码函数清单)、`docs/superpowers/specs/*`(设计)、`docs/superpowers/plans/*`(计划)、`docs/superpowers/gift-followups.md`。

---

## 0. 一句话现状
原始 FH6 脚本(循环跑图/批量买车/专精加点)之上，新增了 **自动送车**、**自动抽奖** 两个功能，重写了 **缩放校准** 使其适配任意窗口分辨率，并把调试功能抽到了 **tools/manualDebug.py**。送车/抽奖/专精在常规窗口下已实机验证通过；当前正在排查 **全屏(3840/1.5×)下"循环跑图"找不到蓝图共享代码输入框** 的问题，以及 **Parsec VDD 断开→黑屏** 的容错。

---

## 1. 必读：关键技术约束（踩过坑，别再踩）
1. **模板基准 2560**：`image_matcher.py` `primary_base=2560`。所有模板**必须在 2560×1440 下截取**（不开 HDR）。运行时按 `当前窗口宽/2560` 缩放适配。
2. **缩放校准以"几何估计 `curr_w/2560`"为准**：实测 UI 随窗宽**线性**缩放（1851→0.723、3134→1.224、3840→1.5 全部精确吻合）。锚点匹配只在"高置信(≥0.62)且与几何值相差±8%内"时做微调；离谱的锚点假峰(如把 1.224 误锁成 0.970)会被**忽略并记日志**。见 `calibrate_match_profile`。
3. **scale>1 时缩小截图、而非放大模板**：`_scale_match_inputs`(image_matcher)。`INTER_AREA` 放大会糊，大照片模板尤其受害。只影响 >2560 窗口，≤2560 零改动。
4. **截屏是整屏 `ImageGrab.grab(all_screens=True)`**：只能截"显示器正在显示的画面"。因此——GUI 窗口盖在游戏上、Parsec VDD 断开变黑屏、关显示器/锁屏，都会导致截到错误/黑画面 → 识别失败。这是当前几个疑难的共同根源。
5. **config 键保持兼容**：专精加点虽从"超级抽奖"重命名，但 config 键仍用 `cj_count`/`chk_3`/`next_3`、任务链步骤 id 仍是 `"cj"`，**不要改**(避免老 config.json 失效)。
6. **大照片模板会随游戏更新失效**：BNandUC 原是含车辆缩略图的大图，游戏更新后失配；已重裁为纯文字。优先用**小文字/图标模板**，别用大照片。
7. **AI/YOLO**：`ai_only/ai_assist/ai_prefer` 控制。YOLO 模型在选车界面训练，礼物界面会失效(送车主要用模板，不依赖 AI)。重训延后。

---

## 2. 各功能代码梳理（按功能；函数名可直接 grep）

### 2.1 自动送车（gift）—— main.py `# --- 模块：自动送车 ---`
- `start_gift_pipeline()`：GUI「自动送车」按钮入口，起线程跑 `logic_gift_duplicate_cars`。
- `logic_gift_duplicate_cars()`：主循环。`navigate_to_giftbox` → `go_to_list_start` → 逐卡决策：全新(`selected_card_has_new_tag`)跳过 / 非目标车(`selected_car_is_target`，含在用 S2-834)跳过 / 否则 `gift_current_car` 送出。失败重试，`NO_PROGRESS_LIMIT=30` 连续不可送即判定送完，`gift_max_count=0` 表示送到没有为止。结束调 `gift_exit_to_menu`。
- `navigate_to_giftbox()`：`enter_menu` → pagedown 进车辆页 → **直接等小模板 `giftbox/giftbox_entry.png`** 确认到位(不用大模板 BNandUC) → 点礼物箱 → 按 `Y` 筛选，下×2+enter 勾「重复项」+esc。
- `find_selected_card_region()`：HSV 黄绿高亮(31,180,210)-(38,255,255)找选中卡区域，随选中卡移动；失败回退 `selected_card_region()`(固定比例框)。
- `selected_card_has_new_tag()`：在选中卡区域找 `newcartag.png`(fast_mode=False)，识别"全新"标记；不确定时安全默认 True(跳过)。
- `selected_car_is_target()` / `gift_panel_conf()`：左侧信息面板**逐字段数值**匹配(马力 `stat_mali`/车重 `stat_chez`/排气 `stat_paiqi`)，取三者最小值，≥0.87 判为目标车。**多尺度扫描**(校准比例×0.85~1.15)适配任意窗口。
- `gift_current_car()`：识别驱动 4 对话框(recipient→msg→sign→confirm)依次 enter → 等 `sent.png`(超时15s，含"正在送出礼物"转圈) → 兜底:确认框消失且回到网格也判成功。先查 `cannot.png`(无法送出=在用车)。debug_mode 下每步存 `debug/gift_seq/`。
- `gift_exit_to_menu()`：按 ESC 后检测主菜单锚点(collectionjournal/horizon6)，到了即停，兜底最多 5 次。
- `go_to_list_start()`：pageup 翻到第一辆，增量间隔帧检测"画面冻结=到顶"。
- 纯逻辑：`gift_logic.py` `should_stop_gifting`/`gift_default_config`(单测 `tests/test_gift_logic.py`)。
- 模板：`images/giftbox/`(giftbox_entry, recipient, msg, sign, confirm, sent, cannot, stat_mali, stat_chez, stat_paiqi) + `images/newcartag.png`。
- config：`gift_max_count`(0=不限)、`chk_gift`(纳入任务链开关)。
- GUI：运行栏「自动送车」按钮 + 送车数量输入框；流程设置面板「送车(纳入链)」开关(纳入链时每轮大循环回环送一次)。

### 2.2 自动抽奖（wheelspin）—— main.py `# --- 模块：自动抽奖 ---`
- `start_wheelspin_pipeline()`：GUI「自动抽奖」按钮入口。
- `navigate_to_wheelspin()`：`enter_menu` → pagedown 切「我的地平线」(menu_anchor) → 按 `wheelspin_mode` 点 `entry_super`/`entry_wheelspin`(彩色匹配区分青/绿底)。点击入口本身会**自动触发第1抽**。
- `logic_auto_wheelspin()`：`spins=1`(入口那抽计入)。循环：`wheelspin_advance_to_result` → 若达 `max_count` 则**最后一抽按 ESC 仅领取**(`collect_only`)+处理已拥有；否则 `collect_and_respin`(点"领取并再抽")触发下一抽、spins+1。
- `wheelspin_advance_to_result()`：**统一高频轮询(~0.12s)**，每帧按优先级查：结果界面(respin，左下提示区→返回) / 已拥有车辆(owned，全屏→下×N+enter 卖出) / 跳过(skip，左下→点击,1s冷却,逐转盘跳) / 退回菜单(每~1s查一次)。这是抽奖稳定的核心：跳过+卖重复车合到一个快循环，避免错过转瞬即逝的跳过窗口。
- `_wheelspin_prompt_region()`：左下角提示区(45%×20%)，skip/respin 只在此搜索→更快更准。
- `collect_and_respin()`/`collect_only()`/`handle_owned_car_dialog()`(首对话框等3.5s其余1.5s)/`is_wheelspin_finished()`(menu_anchor)。
- 纯逻辑：`wheelspin_logic.py`。模板：`images/wheelspin/`(entry_super, entry_wheelspin, menu_anchor, owned, respin, skip)。
- config：`wheelspin_mode`("抽奖"/"超级抽奖")、`wheelspin_max_count`(0=不限)、`wheelspin_owned_downs`(默认2，"已拥有"对话框从默认高亮下几次到"出售")。
- 注意：**超级抽奖是一次性揭晓3张卡**(一个揭晓动画+一个跳过)，不是3个独立转盘。

### 2.3 专精加点（skill-points，原"超级抽奖"）—— main.py
- `logic_skill_points(target_count)`(原 `logic_super_wheelspin`，任务链 `"cj"` 步)：给车辆点专精/技能点。导航→选全新消耗车→上车→升级与调校→点技能。
- `select_new_consumable_car_from_list()`：大范围识别全新消耗车 → `game_click`(=只高亮) → **`selected_car_is_target()` 面板校验**(防误选)不过则跳过继续找 → 通过才上车。
- `wait_for_buy_and_used_car()`(image_matcher)：用 `images/BNandUC.png`(**已重裁为"购买新车与二手车"纯文字**)锚定车辆页。
- 重命名只改了 UI 标签/方法名/日志(超级抽奖/超抽→专精/专精加点)，**config 键 cj_* 未动**。

### 2.4 缩放校准（calibration）—— main.py + image_matcher.py
- `init_match_calibration()`(__init__ 调) / `calibrate_match_profile(force)`：检测到游戏窗口后(在 `check_and_focus_game` 里 `update_regions_by_window` 之后调用)，对一组 2560 锚点(collectionjournal/eventlab/continue-b/continue-w/horizon6/buyandsell-w/designpaint-w/choosecar/rc)多尺度匹配。**preferred_scale 默认=几何 `curr_w/2560`**，锚点仅在高置信+接近几何时微调。窗口签名按 32px 量化 + 60s 去抖(容忍 VDD 抖动)。
- `image_matcher.get_scales_to_try()`：把 `match_calibration["preferred_scale"]` 优先放第一个。
- `image_matcher._scale_match_inputs()`：scale>1 缩小截图、用原生模板(坐标×scale映回)；scale≤1 缩小模板。`find_image_gray`/`find_any_image_gray` 都走它。
- 状态字典 `self.match_calibration`：preferred_scale/state/anchor/anchor_score/window_signature 等。日志 `[Calibration] 已校准(锚点精修)|几何估计(忽略离谱锚点 X@s/score)`。

### 2.5 调试系统 —— tools/manualDebug.py（轻量子类，只注入调试）
- **`python main.py` = 纯净版**(无测试键位、不落盘、不存序列图)。
- **`.venv/Scripts/python.exe tools/manualDebug.py` = 调试版**：`FH_DebugBot(FH_UltimateBot)` 设 `debug_mode=True`，注入调试方法 + 热键。
- 热键(`on_debug_hotkey`)：**F2** 单车送车测试(`gift_one_card_test`) / **F3** 抽奖调试测试(`wheelspin_debug_test`，连抽3次逐步存图) / **F4** 单卡识别(`recognize_current_card`) / **F5** 大范围识别(`recognize_largerange`) / **F6** 整屏截图 / **F7** 诊断打包(`dump_diagnostics`→窗口+校准+日志+整屏) / **F8** 停止 / **F9** 暂停。
- `main.py debug_snap(tag)`：**多显示器失败现场图**(debug_mode)→ `debug/snaps/`：整块虚拟桌面 + 每显示器各一张(文件名带 尺寸+亮度 `bri`，bri≈0=黑屏)。触发点：capture 黑屏告警(`_warn_capture` ≤1/5s)、送车/抽奖导航失败、跑图 advanced_menu/recovery 失败、蓝图 sharecode 失败。
- `image_matcher._warn_capture()`：截屏全黑/彻底失败 限频日志 `[Capture]`，并触发 debug_snap。
- 调试产物目录：`debug/gui_log.txt`、`debug/snaps/`、`debug/gift_seq/`、`debug/wheelspin_seq/`、`debug/diagnostics/`。

---

## 3. 已完成 / 已修复（按时间脉络）
- 环境：venv 重建(`.venv/Scripts/python.exe`)；恢复 F9 暂停；建上游 `mystic` 同步。
- 送车：全套识别管线(导航/Y筛选/动态高亮跟踪/全新检测/目标车面板/归位) + 识别驱动4对话框真实送出 + 批量循环(重试/无进展终止/在用车跳过) + 退回主菜单。
- 抽奖：完整流程 + 计数修正(入口计第1抽、最后一抽 ESC) + **统一高频轮询**(逐转盘跳过、卖重复车合一) + 左下提示区限定。
- 专精：选中卡面板校验防误选。
- 缩放校准：兜底由 1.0 改**几何 curr_w/2560**；再改为**几何为准、忽略离谱锚点假峰**(解决 3134/3840 下 panel/识别)。
- 矩阵改进：scale>1 **缩小截图而非放大模板**。
- 导航修复：送车改用 `giftbox_entry` 锚定(大窗口下 BNandUC 失配)；专精 `BNandUC` **重裁为文字模板**(游戏更新致旧大照片失配)。
- 重命名：超级抽奖→专精加点(保留 config 键)。
- GUI：标题 `mysticEe v0.2`；停止/暂停移到守护设置栏；模块累计加 送车/抽奖耗时；送车任务卡+次数+任务链开关。
- 上游吸取：自适应校准(用我们2560锚点)、评价弹窗 `handle_author_prompt` 轮询等待(c0baca7)、深挖 Finding A(障碍目录用 `get_img_path` 绝对路径)。**未取**上游 `images/1080p/`(基准不同会崩)。
- 模板修整：`stat_paiqi` 去掉右侧黄色残片。
- 调试：抽离 manualDebug.py + F3抽奖测试 + F7诊断 + 多显示器失败存图 + 黑屏告警。

---

## 4. 进行中 / 待办 / 已知问题
### 4.1 当前正在排查（最高优先）
- **全屏(3840,scale1.5)下"循环跑图"找不到蓝图共享代码输入框**(`sharecode-dialog.png` 在 `regions["中间"]` 未命中)。全屏下菜单导航全部正常(collectionjournal/eventlab/playenent 0.9+)，唯独此处失败。窗口模式下原本是好的。
  - 已在真实失败点加 `debug_snap("sharecode_dialog_fail")`(恢复前存图)。**下一步**：全屏复现，看 `debug/snaps/*sharecode_dialog_fail*` 判断是"对话框在屏上但模板没匹配(模板/缩放/样式)"还是"对话框没弹出(导航问题)"。
- **Parsec VDD 断开→黑屏**：Parsec 断开后该虚拟显示器内容变黑(brightness 掉到≈0~85)且分辨率会跳变(1964↔3449↔3840)，导致识别全失败、跑图卡死。日志已有 `[Capture] 截屏几乎全黑` 时间线 + 多显示器现场图。
  - **方案**：① 治本——用独立常驻 VDD(如 ParsecVDisplay/nomi-san parsec-vdd)挂一块不随 Parsec 存亡的虚拟屏；② 兜底——bot 检测黑屏→调用命令重建显示器(需用户装可命令行控制的工具)；③ 容错——黑屏不立即停，暂停等画面回来再续跑(纯 bot 侧，待实现)。
- **焦点丢失**：游戏窗口失焦后，按键/点击会发到桌面/别的窗口(曾导致桌面弹出右键菜单、ESC 不进游戏)。`check_and_focus_game` 不是每步都调。考虑每次关键操作前强制确保游戏前台。

### 4.2 待办（已确认方案，未做）
- **键盘布局污染**：`set_english_input()` 用 `LoadKeyboardLayoutW("00000409")` 把"ENG US"塞进了系统(用户原生是 ENG INTL/US-International 00020409)。**方案A(选定)**：去掉 LoadKeyboardLayout，只保留关中文输入法状态(`IMC_SETOPENSTATUS=0`)。改完需手动删 `HKCU:\Keyboard Layout\Preload` 里的 `00000409` 并重登。
- 黑屏容错(暂停/续跑)。
- 上游深挖里的其它低价值项(暂不取)。

### 4.3 延后
- YOLO 重训(覆盖礼物界面/区分车款，需 GPU/云 + 采图，见 gift-followups.md)。
- 分支合并到 main(最后做)。

### 4.4 与仓库无关（用户本机操作，记此备忘）
- 用户用 Parsec VDD 虚拟显示器(+物理屏 32M2N8800)远程；关 Claude 全屏设置是用户本机的事。

---

## 5. 如何运行与调试（换电脑后照此做）
1. venv：`.venv/Scripts/python.exe`(注意是 Scripts 不是 Script)。缺则用 Python 3.14 重建并 `pip install -r requirements.txt`(若有)。
2. 纯净运行：`.venv/Scripts/python.exe main.py`。
3. **调试运行**：`.venv/Scripts/python.exe tools/manualDebug.py` → 用 F2~F7 热键，产物在 `debug/`。
4. 改完务必 `.venv/Scripts/python.exe -m py_compile main.py image_matcher.py ui_layout.py` + `python -m unittest tests.test_gift_logic tests.test_wheelspin_logic`。
5. 裁模板：必须 2560×1440 源，cv2 读中文路径要用 `np.fromfile+imdecode`(cv2.imread 不支持中文路径)。裁完务必**肉眼 Read 一下 PNG 确认内容**(自匹配 conf=1.0 不能证明对)。
6. 排查识别问题：优先看 `debug/snaps/` 现场图(文件名 `bri` 看黑屏) + `debug/gui_log.txt` 的 `[Calibration]`/`[Capture]`/`[GrayMatch] 缩放比`。

---

## 6. 给接手的 Claude 的提示
- 用户中文沟通，重实证("不要靠猜")——遇问题先取**日志+截图**再下结论(本会话有过"用错截图下早了结论"的教训：恢复后的截图≠失败那刻的截图，要在**真实失败点**存图)。
- 改动小步提交、每次 py_compile + 单测；阶段性推 `mystic` 备份。
- 多代理可并行(本会话用过 worktree 隔离子代理做抽奖/校准/上游分析)，但都改 main.py 会有合并成本。
