# 自动送车 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「自动送车」流程：进入礼物箱、筛选重复项、把所有无「全新标记」的重复车送掉，到「无法送出」提示为止。

**Architecture:** 纯决策逻辑抽到无 GUI 依赖的 `gift_logic.py`（可单测）；I/O 流程方法 `logic_gift_duplicate_cars` 加入 `main.py`，复刻现有 `logic_super_wheelspin` 写法，复用既有识图/输入工具；标准模板匹配（2560 基准）+ `newcartag.png` 识别全新标记；独立 GUI 按钮触发。

**Tech Stack:** Python 3.14、OpenCV 模板匹配、customtkinter GUI、pydirectinput/pynput 输入、stdlib `unittest`。

## Global Constraints

- 识图模板基准 **2560×1440**（`image_matcher.py:208` `primary_base = 2560`，多尺度匹配自动适配运行分辨率）。新模板从 `E:\FH6\screenshots\NN_*.png`（2560×1440）裁取。
- **安全红线**：送车前必须确认选中卡无「全新标记」；识别不确定时一律**跳过不送**（漏送可接受，误送不可接受）。
- 复用现有工具，不新增底层机制：`enter_menu`/`game_click`/`hw_press`/`wait_for_image_gray`/`find_image_gray`/`wait_for_any_image_gray`/`capture_region`/`check_pause`/`update_running_ui`/`check_and_focus_game`/`ui_call`。
- 流程方法签名遵循现有约定：`def logic_xxx(self, ...) -> bool`（返回是否成功），内部循环顶部判 `if not self.is_running: return False` 并调用 `self.check_pause()`。
- 提交信息以 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` 结尾。
- 运行 Python 用 venv：`.venv/Scripts/python.exe`。

## 设计参考

- 设计文档：`docs/superpowers/specs/2026-06-24-auto-gift-cars-design.md`
- 截图（2560×1440）：`screenshots/01_主菜单` … `13_无法送出提示`（送车段 01-13）
- 流程：主菜单→车辆页→礼物箱→`F`筛选→`下`×2`Enter`勾「重复项」`Esc`→网格逐卡：选中卡查全新→无则赠送序列（`Enter`选→`Enter`任何人→`Enter`话语→`Enter`名称→等「礼物已送出」→`Enter`）→下一张→出现「无法送出」停止。

## File Structure

- **Create `gift_logic.py`** — 纯决策函数（无 GUI/cv2 依赖），`should_stop_gifting`、`gift_default_config`。
- **Create `tests/test_gift_logic.py`** — `unittest` 测试纯逻辑。
- **Create `tools/verify_template.py`** — 对静态截图跑模板匹配，验证裁出的模板能命中。
- **Create `images/giftbox/*.png`** — 新模板：`entry.png`、`grid.png`、`filter_title.png`、`recipient.png`、`sent.png`、`cannot.png`。
- **Modify `main.py`** — 新增 `logic_gift_duplicate_cars` 及辅助方法、`start_gift_pipeline`；config 默认加 `gift_max_count`。
- **Modify `ui_layout.py`** — 新增「自动送车」按钮。

---

### Task 1: 纯决策逻辑 `gift_logic.py` + 单测

**Files:**
- Create: `gift_logic.py`
- Test: `tests/test_gift_logic.py`

**Interfaces:**
- Produces:
  - `should_stop_gifting(*, cannot_gift_detected: bool, remaining_cards: int, gifted_count: int, max_count: int) -> tuple[bool, str]` — 返回 `(should_stop, reason)`。
  - `gift_default_config() -> dict` — 返回 `{"gift_max_count": 200}`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gift_logic.py
import unittest
from gift_logic import should_stop_gifting, gift_default_config


class TestShouldStopGifting(unittest.TestCase):
    def _ok(self, **kw):
        base = dict(cannot_gift_detected=False, remaining_cards=20,
                    gifted_count=0, max_count=200)
        base.update(kw)
        return should_stop_gifting(**base)

    def test_continue_normal(self):
        stop, reason = self._ok()
        self.assertFalse(stop)
        self.assertEqual(reason, "")

    def test_stop_on_cannot_gift(self):
        stop, reason = self._ok(cannot_gift_detected=True)
        self.assertTrue(stop)
        self.assertIn("无法送出", reason)

    def test_stop_on_single_card_left(self):
        stop, reason = self._ok(remaining_cards=1)
        self.assertTrue(stop)
        self.assertIn("仅剩", reason)

    def test_stop_on_max_count(self):
        stop, reason = self._ok(gifted_count=200, max_count=200)
        self.assertTrue(stop)
        self.assertIn("上限", reason)

    def test_max_count_zero_means_unlimited(self):
        stop, reason = self._ok(gifted_count=99999, max_count=0)
        self.assertFalse(stop)

    def test_cannot_gift_takes_priority(self):
        stop, reason = self._ok(cannot_gift_detected=True, remaining_cards=1)
        self.assertTrue(stop)
        self.assertIn("无法送出", reason)


class TestDefaultConfig(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(gift_default_config(), {"gift_max_count": 200})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m unittest tests.test_gift_logic -v`
Expected: FAIL —`ModuleNotFoundError: No module named 'gift_logic'`

- [ ] **Step 3: 写最小实现**

```python
# gift_logic.py
"""自动送车流程的纯决策逻辑（无 GUI / OpenCV 依赖，便于单测）。"""


def should_stop_gifting(*, cannot_gift_detected, remaining_cards,
                        gifted_count, max_count):
    """判断送车循环是否应停止。返回 (should_stop, reason)。

    优先级：无法送出提示 > 仅剩1卡 > 达到数量上限。
    max_count == 0 表示不限数量。
    """
    if cannot_gift_detected:
        return True, "检测到「无法送出」提示，列表已送完"
    if remaining_cards <= 1:
        return True, "网格仅剩 1 张卡，已送完"
    if max_count and gifted_count >= max_count:
        return True, f"达到最大赠送数量上限 {max_count}"
    return False, ""


def gift_default_config():
    """送车功能写入 config 的默认项。"""
    return {"gift_max_count": 200}
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/Scripts/python.exe -m unittest tests.test_gift_logic -v`
Expected: PASS（6 个测试全过）

- [ ] **Step 5: 提交**

```bash
git add gift_logic.py tests/test_gift_logic.py
git commit -m "feat(gift): pure stop-condition logic with unit tests"
```

---

### Task 2: 裁取模板素材 + 静态验证脚本

**Files:**
- Create: `tools/verify_template.py`
- Create: `images/giftbox/entry.png`, `grid.png`, `filter_title.png`, `recipient.png`, `sent.png`, `cannot.png`

**Interfaces:**
- Produces: `images/giftbox/*.png` 模板；`tools/verify_template.py`（命令行：`python tools/verify_template.py <模板> <截图> [阈值]`，打印匹配置信度与位置，命中返回 exit 0）。

> 说明：模板裁取是**视觉迭代**任务。下面给出每个模板的来源截图与大致区域；实现时打开截图按实际像素微调裁框，再用验证脚本确认命中。全新标记**复用现有 `images/newcartag.png`**，不在此裁。

- [ ] **Step 1: 写验证脚本**

```python
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
    for scale in [1.0, 0.98, 1.02, 0.95, 1.05, 0.92, 1.08, 0.9, 1.1]:
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
```

- [ ] **Step 2: 裁 `entry.png`（礼物箱入口）**

来源 `screenshots/02_礼物箱入口_车辆页.png`，裁中间列「礼物箱」文字所在小块（约该列第 3 行）。用 PIL 裁框示例（坐标按实际微调）：

```python
# 临时裁图（在 .venv python 交互或一次性脚本中执行）
from PIL import Image
im = Image.open("screenshots/02_礼物箱入口_车辆页.png")
# 区域 (left, top, right, bottom)，按截图实际像素调整
im.crop((760, 690, 1010, 740)).save("images/giftbox/entry.png")
```

- [ ] **Step 3: 验证 `entry.png` 命中**

Run: `.venv/Scripts/python.exe tools/verify_template.py images/giftbox/entry.png "screenshots/02_礼物箱入口_车辆页.png" 0.7`
Expected: `RESULT: 命中 ✓`（conf ≥ 0.7）。未命中则回 Step 2 调裁框。

- [ ] **Step 4: 同法裁并验证其余模板**

| 模板 | 来源截图 | 取景内容 |
|---|---|---|
| `grid.png` | `03_礼物箱刚进入.png` | 左上「礼物选择」标题块（判进入网格） |
| `filter_title.png` | `04_筛选界面.png` | 顶部「筛选」标题块（判筛选菜单已开） |
| `recipient.png` | `06_第一次enter_将礼物赠送给.png` | 「将礼物赠送给」标题块（判进入赠送序列） |
| `sent.png` | `11_礼物已送出提示.png` | 「礼物已送出」标题块（判一次赠送成功） |
| `cannot.png` | `13_无法送出提示.png` | 「您不能将此车作为礼物赠送」标题块（停止主信号） |

每张裁完后运行 `verify_template.py` 对应截图，确认 `命中 ✓`。

- [ ] **Step 5: 提交**

```bash
git add tools/verify_template.py images/giftbox/
git commit -m "feat(gift): add giftbox templates and static match verifier"
```

---

### Task 3: 导航进入礼物箱 `navigate_to_giftbox`

**Files:**
- Modify: `main.py`（在 `logic_super_wheelspin` 之后、模块区内新增方法）

**Interfaces:**
- Consumes: `enter_menu()`, `wait_for_image_gray(template, region, threshold, timeout, interval, fast_mode)`, `game_click(pos)`, `hw_press(key, delay)`, `self.regions["全界面"]`, `check_pause()`, `log()`.
- Produces: `navigate_to_giftbox(self) -> bool` — 进入礼物箱并应用「重复项」筛选，成功返回 True。

- [ ] **Step 1: 写实现**

```python
    # ==========================================
    # --- 模块：自动送车 ---
    # ==========================================
    def navigate_to_giftbox(self):
        """进入主菜单 → 车辆页 → 礼物箱 → F筛选 → 勾「重复项」。成功返回 True。"""
        self.log("[Gift] 准备进入主菜单...")
        if not self.enter_menu():
            self.log("[Gift] 进入主菜单失败。")
            return False

        # 切到「车辆」标签页并定位礼物箱入口（复用跑图导航的翻页/锚点模式）
        pos_entry = None
        for _ in range(6):
            if not self.is_running:
                return False
            self.check_pause()
            pos_entry = self.wait_for_image_gray(
                "giftbox/entry.png", region=self.regions["全界面"],
                threshold=0.7, timeout=1.5, interval=0.2, fast_mode=True)
            if pos_entry:
                break
            self.hw_press("pagedown", delay=0.15)
            time.sleep(0.4)
        if not pos_entry:
            self.log("[Gift] 未找到礼物箱入口。")
            return False
        self.game_click(pos_entry)
        time.sleep(1.5)

        # 确认进入礼物选择网格
        if not self.wait_for_image_gray("giftbox/grid.png", region=self.regions["全界面"],
                                        threshold=0.7, timeout=8, interval=0.25, fast_mode=True):
            self.log("[Gift] 未进入礼物选择网格。")
            return False

        # 打开筛选并勾选「重复项」（F → 下×2 → Enter → Esc）
        self.hw_press("f")
        time.sleep(0.8)
        if not self.wait_for_image_gray("giftbox/filter_title.png", region=self.regions["全界面"],
                                        threshold=0.7, timeout=5, interval=0.25, fast_mode=True):
            self.log("[Gift] 未打开筛选菜单。")
            return False
        self.hw_press("down", delay=0.12)
        self.hw_press("down", delay=0.12)
        self.hw_press("enter", delay=0.12)   # 勾选「重复项」
        time.sleep(0.5)
        self.hw_press("esc")
        time.sleep(1.2)
        self.log("[Gift] 已进入礼物箱并应用「重复项」筛选。")
        return True
```

- [ ] **Step 2: 语法编译检查**

Run: `.venv/Scripts/python.exe -m py_compile main.py`
Expected: 无输出（编译通过）

- [ ] **Step 3: 实机手动验证**

启动游戏（停在任意界面）→ GUI 启动后临时绑定按钮触发 `navigate_to_giftbox`。
观察：脚本能进入礼物箱、网格只剩重复车。**记录是否需要调整 `pagedown` 次数 / 阈值**。

- [ ] **Step 4: 提交**

```bash
git add main.py
git commit -m "feat(gift): navigate to giftbox and apply duplicate filter"
```

---

### Task 4: 全新标记检测 `selected_card_has_new_tag`

**Files:**
- Modify: `main.py`（模块区内，紧接 Task 3）

**Interfaces:**
- Consumes: `find_image_gray("newcartag.png", region, threshold, fast_mode)`，选中卡区域坐标（左上高亮卡）。
- Produces: `selected_card_has_new_tag(self) -> bool` — 选中卡**有**全新标记或**识别不确定**时返回 True（安全默认）。

- [ ] **Step 1: 标定选中卡区域**

打开 `screenshots/05_筛选重复后.png` 与 `12_带全新标记的车辆卡片.png`，量出左上高亮卡的「全新」标记所在小区域（2560 坐标，转为相对全界面的比例）。示例脚本打印比例：

```python
# 一次性：根据像素框换算比例 (x,y,w,h) / (2560,1440)
L, T, R, B = 150, 360, 600, 700   # 选中卡范围，按截图实测填入
print((L/2560, T/1440, (R-L)/2560, (B-T)/1440))
```

记录得到的比例，用于 Step 2 的 region 计算。

- [ ] **Step 2: 写实现**

```python
    def selected_card_region(self):
        """选中卡（左上高亮卡）区域，按全界面比例换算（比例由 Task4-Step1 标定）。"""
        x, y, w, h = self.regions["全界面"]
        # 下列比例为占位，需替换为 Step 1 实测值
        rx, ry, rw, rh = 0.058, 0.250, 0.176, 0.236
        return (x + int(w * rx), y + int(h * ry), int(w * rw), int(h * rh))

    def selected_card_has_new_tag(self):
        """选中卡是否带「全新」标记。识别不确定时返回 True（安全默认：不送）。"""
        try:
            region = self.selected_card_region()
            pos = self.find_image_gray("newcartag.png", region=region,
                                       threshold=0.68, fast_mode=True)
            return pos is not None
        except Exception as e:
            self.log(f"[Gift] 全新标记检测异常，按有标记处理: {e}")
            return True
```

- [ ] **Step 3: 静态验证（对截图）**

写一次性脚本，分别对「带全新标记」和「不带」的选中卡截图跑 `newcartag.png` 匹配，确认：带标记截图命中、不带的不命中。

Run: `.venv/Scripts/python.exe tools/verify_template.py images/newcartag.png "screenshots/12_带全新标记的车辆卡片.png" 0.68`
Expected: 命中 ✓（该图右侧列有全新标记）。再对 `05_筛选重复后.png`（选中卡无标记）应**未命中或置信明显更低**。

- [ ] **Step 4: 语法编译检查**

Run: `.venv/Scripts/python.exe -m py_compile main.py`
Expected: 编译通过

- [ ] **Step 5: 提交**

```bash
git add main.py
git commit -m "feat(gift): detect 全新 tag on selected card (safe-default skip)"
```

---

### Task 5: 单辆赠送序列 `gift_current_car`

**Files:**
- Modify: `main.py`（模块区内，紧接 Task 4）

**Interfaces:**
- Consumes: `hw_press`, `wait_for_image_gray("giftbox/recipient.png"|"giftbox/sent.png")`, `find_image_gray("giftbox/cannot.png")`, `check_pause`, `log`.
- Produces: `gift_current_car(self) -> str` — 执行选中卡赠送序列，返回 `"sent"`（成功）/`"cannot"`（无法送出）/`"fail"`（异常/超时）。

- [ ] **Step 1: 写实现**

```python
    def gift_current_car(self):
        """对当前选中卡执行赠送序列。返回 'sent' / 'cannot' / 'fail'。"""
        self.hw_press("enter")          # 选中卡 → 弹「将礼物赠送给」或「无法送出」
        time.sleep(0.8)

        # 优先判定「无法送出」（停止主信号）
        if self.find_image_gray("giftbox/cannot.png", region=self.regions["全界面"],
                                 threshold=0.7, fast_mode=True):
            self.log("[Gift] 检测到「无法送出」。")
            self.hw_press("enter")      # 关掉提示
            time.sleep(0.6)
            return "cannot"

        # 确认进入赠送序列
        if not self.wait_for_image_gray("giftbox/recipient.png", region=self.regions["全界面"],
                                        threshold=0.7, timeout=4, interval=0.2, fast_mode=True):
            self.log("[Gift] 未进入赠送对话框，跳过本卡。")
            return "fail"

        # 默认：任何人 → 话语 → 名称
        for _ in range(3):
            self.check_pause()
            self.hw_press("enter")
            time.sleep(0.7)

        # 等「礼物已送出」成功提示（含转圈 1-3 秒）
        if not self.wait_for_image_gray("giftbox/sent.png", region=self.regions["全界面"],
                                        threshold=0.7, timeout=8, interval=0.25, fast_mode=True):
            self.log("[Gift] 未出现「礼物已送出」，按失败处理。")
            return "fail"
        self.hw_press("enter")          # 确定 → 回到网格
        time.sleep(1.0)
        return "sent"
```

- [ ] **Step 2: 语法编译检查**

Run: `.venv/Scripts/python.exe -m py_compile main.py`
Expected: 编译通过

- [ ] **Step 3: 提交**

```bash
git add main.py
git commit -m "feat(gift): single-car gift Enter sequence with sent/cannot result"
```

---

### Task 6: 主循环 `logic_gift_duplicate_cars`

**Files:**
- Modify: `main.py`（模块区内，紧接 Task 5；顶部 `from gift_logic import should_stop_gifting`）

**Interfaces:**
- Consumes: Task1 `should_stop_gifting`；Task3 `navigate_to_giftbox`；Task4 `selected_card_has_new_tag`；Task5 `gift_current_car`；`update_running_ui`, `check_pause`, `find_image_gray("giftbox/grid.png")`。
- Produces: `logic_gift_duplicate_cars(self) -> bool`。

- [ ] **Step 1: 在 main.py 顶部加导入**

```python
from gift_logic import should_stop_gifting, gift_default_config
```

- [ ] **Step 2: 写主循环实现**

```python
    def logic_gift_duplicate_cars(self):
        """自动送车主流程：送掉所有无全新标记的重复车，到「无法送出」为止。"""
        if not self.navigate_to_giftbox():
            return False

        try:
            max_count = int(self.config.get("gift_max_count", 200))
        except Exception:
            max_count = 200

        gifted = 0
        consecutive_skips = 0
        SKIP_LIMIT = 60   # 连续这么多张都是全新/失败则认为到边界，停止
        self.update_running_ui("自动送车", gifted, max_count or 0)

        while self.is_running:
            self.check_pause()

            # 估算剩余卡（网格锚点是否还在；只剩个位数时锚点形态变化作为辅助）
            grid_present = self.find_image_gray(
                "giftbox/grid.png", region=self.regions["全界面"],
                threshold=0.7, fast_mode=True) is not None
            remaining = 99 if grid_present else 1

            stop, reason = should_stop_gifting(
                cannot_gift_detected=False, remaining_cards=remaining,
                gifted_count=gifted, max_count=max_count)
            if stop:
                self.log(f"[Gift] 停止：{reason}")
                break

            if self.selected_card_has_new_tag():
                self.hw_press("right", delay=0.1)   # 全新，跳到下一张
                time.sleep(0.3)
                consecutive_skips += 1
                if consecutive_skips >= SKIP_LIMIT:
                    self.log("[Gift] 连续大量跳过，判定无更多可送车，停止。")
                    break
                continue

            result = self.gift_current_car()
            if result == "sent":
                gifted += 1
                consecutive_skips = 0
                self.update_running_ui("自动送车", gifted, max_count or 0)
                self.log(f"[Gift] 已送出 {gifted} 辆。")
            elif result == "cannot":
                self.log("[Gift] 已送完（无法送出）。")
                break
            else:  # fail
                consecutive_skips += 1
                self.hw_press("right", delay=0.1)
                time.sleep(0.3)
                if consecutive_skips >= SKIP_LIMIT:
                    self.log("[Gift] 连续失败过多，停止以防异常。")
                    break

        self.log(f"[Gift] 送车流程结束，共送出 {gifted} 辆。")
        return True
```

- [ ] **Step 3: 语法编译检查**

Run: `.venv/Scripts/python.exe -m py_compile main.py gift_logic.py`
Expected: 编译通过

- [ ] **Step 4: 提交**

```bash
git add main.py
git commit -m "feat(gift): main gift loop wiring detection/sequence/stop logic"
```

---

### Task 7: 独立启动器 + GUI 按钮 + 配置

**Files:**
- Modify: `main.py`（新增 `start_gift_pipeline`；config 默认合并 `gift_default_config()`）
- Modify: `ui_layout.py`（新增「自动送车」按钮）

**Interfaces:**
- Consumes: Task6 `logic_gift_duplicate_cars`；`check_and_focus_game`, `is_running`, `update_running_state`, `reset_run_stats`, `update_timer`, `stop_all`, `save_config`。
- Produces: `start_gift_pipeline(self)`（GUI 按钮回调）。

- [ ] **Step 1: 写独立启动器（仿 `start_test_find_image`）**

```python
    def start_gift_pipeline(self):
        if self.is_running:
            self.log("已有任务正在运行，无法启动送车。")
            return
        self.is_running = True
        self.is_paused = False
        self.save_config()
        self.reset_run_stats()
        self.update_running_state("running")
        self.update_running_ui("自动送车", 0, 0)
        self.update_timer()
        self.log("====== 开始自动送车 ======")

        def runner():
            try:
                if not self.check_and_focus_game():
                    self.log("未能聚焦游戏窗口，送车结束。")
                    return
                self.logic_gift_duplicate_cars()
            except Exception as e:
                self.log(f"送车流程异常: {e}")
            finally:
                self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()
```

- [ ] **Step 2: config 默认项合并**

在 `load_config` 的默认字典里加入 `gift_max_count`。定位默认字典（含 `"race_timeout": 300,` 等的块），加入一行：

```python
            "gift_max_count": 200,
```

- [ ] **Step 3: GUI 按钮**

在 `ui_layout.py` 运行控制区（`runtime_frame`，pause/stop 按钮附近）新增按钮（放在 `btn_runtime_pause` 之前）：

```python
    bot.btn_runtime_gift = button(
        bot.runtime_frame,
        "自动送车",
        bot.start_gift_pipeline,
        color=colors["purple"],
        hover=colors["purple_hover"],
        width=92,
        height=34,
    )
    bot.btn_runtime_gift.pack(side="right", padx=(0, 8), pady=14)
```

- [ ] **Step 4: 语法编译检查**

Run: `.venv/Scripts/python.exe -m py_compile main.py ui_layout.py`
Expected: 编译通过

- [ ] **Step 5: GUI 启动冒烟（不连游戏）**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('main.py',encoding='utf-8').read()); ast.parse(open('ui_layout.py',encoding='utf-8').read()); print('AST OK')"`
Expected: `AST OK`。再启动 GUI 目视确认「自动送车」按钮出现（手动启动 `main.py`）。

- [ ] **Step 6: 提交**

```bash
git add main.py ui_layout.py
git commit -m "feat(gift): standalone launcher, GUI button, gift_max_count config"
```

---

### Task 8: 实机端到端验证 + 参数微调

**Files:** 无新增（仅按需微调 Task 3-6 的阈值/等待/比例）

- [ ] **Step 1: 实机跑完整送车**

游戏 1080P/2560 任一、不开 HDR，车库有若干重复车（含个别全新）。点「自动送车」。

- [ ] **Step 2: 核对安全红线**

确认：带全新标记的车**未被送出**；无标记重复车被送掉；最后出现「无法送出」后**自动停止**。

- [ ] **Step 3: 按观察微调**

如有误判/卡顿，调整：`selected_card_region` 比例、各 `threshold`、赠送序列 `time.sleep`、`pagedown`/`SKIP_LIMIT`。每次改后重跑验证。

- [ ] **Step 4: 回归单测**

Run: `.venv/Scripts/python.exe -m unittest tests.test_gift_logic -v`
Expected: 全过。

- [ ] **Step 5: 提交微调**

```bash
git add -A
git commit -m "fix(gift): tune thresholds/regions after live verification"
```

---

## Self-Review

**Spec coverage（对 `2026-06-24-auto-gift-cars-design.md`）：**
- §4.1 导航 → Task 3 ✓
- §4.2 逐卡先验后送 → Task 4（检测）+ Task 6（循环）✓
- §4.3 赠送序列 → Task 5 ✓
- §4.4 停止条件（无法送出/仅剩1卡/上限）→ Task 1（纯逻辑）+ Task 5/6（接入）✓
- §5 接入（GUI 按钮）→ Task 7 ✓
- §6 模块拆分（navigate/has_new_tag/gift_current/stop）→ Task 3-6 一一对应 ✓
- §7 配置 `gift_max_count` → Task 7 ✓
- §8 素材（模板）→ Task 2 ✓
- §9 安全红线 → Task 4 安全默认 + Task 8 核对 ✓
- 任务链集成（§5 可选）→ **本计划 V1 不含**，作为后续独立计划（见下）。

**范围说明：** 任务链集成（把送车作为第 4 步纳入 `start_pipeline`）改动核心调度，风险与收益不对称，V1 以独立按钮交付；待按钮版稳定后另开计划处理。

**Placeholder 扫描：** Task 2 模板裁框坐标、Task 4 `selected_card_region` 比例为**实测占位**，已显式标注「需替换为实测值」并配套验证步骤——属图像标定的固有性质，非逻辑占位。

**类型一致性：** `gift_current_car` 返回 `"sent"/"cannot"/"fail"` 在 Task 6 全部分支处理 ✓；`should_stop_gifting` 返回 `(bool, str)` 在 Task 6 解包 ✓。
