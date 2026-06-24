# FH6 代码库认知地图 (CODEBASE_MAP)

> 由完整通读原始代码生成的函数清单，供开发新功能时判断"哪些可复用、哪些要新建"。
> 覆盖 main.py / image_matcher.py / ui_layout.py / app_resources.py 全部原始函数（不含新增送车段）。
> 生成日期：2026-06-25。


---

# image_matcher.py — 识图工具层 (ImageMatcherMixin)

# image_matcher.py — 函数清单

## 总览

`image_matcher.py`（1965 行）实现了 `ImageMatcherMixin`，为 Forza Horizon 6 自动化 bot 提供全套屏幕截图 + 模板匹配能力。核心能力分三层：**截图与缓存**（capture + 多级模板缓存）、**匹配算法**（单图/多图/灰度/透明/边缘/二阶组合/终极安全锁五种路径）、**业务封装**（wait_for_* 轮询包装、刷图车辨别、严格新车检测、F3 测试线束）。整个 Mixin 无构造函数，依赖宿主类提供 `self.is_running`、`self.regions`、`self.config`、`self.template_cache`、`self.scaled_template_cache`、`self.file_template_cache` 等属性。所有坐标均以屏幕绝对像素返回，匹配默认以 2560px 宽度为基准进行多尺度缩放。

### 最值得直接复用的 10 个函数

- `find_image` — 最常用的单图全尺度彩色匹配入口
- `find_any_image` — 一次截图顺序匹配多张候选图
- `wait_for_image` / `wait_for_any_image` — 带超时轮询的 find_image 封装
- `find_image_gray` / `wait_for_image_gray` — 灰度匹配（支持反相），抗 HDR 干扰
- `find_image_with_element_multi` — 五维评分的二阶组合匹配，专为带标签的车辆卡片设计
- `find_image_ultimate_safe` — 三道防线（排他+顶部文字+右下调校）终极安全锁
- `find_image_transparent` / `wait_for_image_transparent` — 带 Alpha 遮罩的透明背景匹配
- `capture_region` — 屏幕截图（支持区域遮罩），所有匹配函数的共同基础
- `match_template_score` — 单次 TM_CCOEFF_NORMED 打分，用于嵌入自定义管道
- `find_new_consumable_car_strict` — 全新+B600+车辆卡三重验证，适配消耗车检测逻辑

---

## 分组：模块顶层工具函数

### `cv2_imread(path, flags=cv2.IMREAD_COLOR)` — image_matcher.py:23
- **作用**: 用 `np.fromfile` 绕过 OpenCV 不支持非 ASCII 路径的问题，安全读取图片。
- **实现**: 1. `np.fromfile` 读取字节 → `cv2.imdecode` 解码；2. 失败降级到 `cv2.imread`。
- **关键参数**: `flags` 默认 `cv2.IMREAD_COLOR`，传 `cv2.IMREAD_GRAYSCALE` 或 `cv2.IMREAD_UNCHANGED` 可读灰度/透明图。
- **复用价值**: 高 — 凡需读取含中文路径图片均可直接替换 `cv2.imread`。

---

## 分组：模板缓存管理

### `load_template(self, template_path)` — image_matcher.py:35
- **作用**: 按路径加载彩色模板，结果存入内存字典 `self.template_cache`。
- **实现**: 1. `get_img_path` 解析实际路径；2. 命中 `template_cache` 直接返回；3. 未命中调用 `cv2_imread` 读取并缓存。
- **关键参数**: `template_path` 为相对或绝对路径。
- **复用价值**: 中 — 通常由更高层函数间接调用，手动调用可预热缓存。

### `load_template_gray(self, template_path)` — image_matcher.py:46
- **作用**: 加载灰度模板，结果存入 `self.template_gray_cache`（懒初始化）。
- **实现**: 1. 组合 key `("gray", actual_path)`；2. `cv2.IMREAD_GRAYSCALE` 读取并缓存。
- **关键参数**: `template_path`。
- **复用价值**: 中 — 灰度匹配路径的基础，频繁被 `find_image_gray` 系列调用。

### `load_template_transparent(self, template_path)` — image_matcher.py:916
- **作用**: 加载保留 Alpha 通道（BGRA）的模板，存入 `self.template_transparent_cache`。
- **实现**: 1. 组合 key `("transparent", actual_path)`；2. `cv2.IMREAD_UNCHANGED` 读取，保留第 4 通道。
- **关键参数**: `template_path`。
- **复用价值**: 中 — 透明背景匹配的专用加载器，仅配合 `find_image_transparent` 系列使用。

### `get_images_root_dir(self)` — image_matcher.py:57
- **作用**: 返回 images 目录的绝对路径，优先外部 `APP_DIR/images`，回退到 `INTERNAL_DIR/images`。
- **实现**: 两次 `os.path.isdir` 检查，均不存在返回 `None`。
- **关键参数**: 无。
- **复用价值**: 低 — 内部基础设施，一般不直接调用。

### `get_template_meta(self)` — image_matcher.py:68
- **作用**: 遍历 images 目录，收集所有图片文件的相对路径、mtime 和 size，用于缓存有效性校验。
- **实现**: `os.walk` 递归遍历 → 过滤图片扩展名 → 记录 `stat.st_mtime` 和 `stat.st_size`。
- **关键参数**: 无。
- **复用价值**: 低 — 仅供 `is_template_cache_valid` 调用。

### `is_template_cache_valid(self)` — image_matcher.py:93
- **作用**: 比较磁盘上的 meta JSON 与当前目录状态，判断模板缓存是否过期。
- **实现**: 读 `TEMPLATE_META_FILE` → `json.load` → 与 `get_template_meta()` 结果做 `==` 比较。
- **关键参数**: 无。
- **复用价值**: 低 — 仅供 `prepare_template_cache` 调用。

### `build_template_file_cache(self)` — image_matcher.py:106
- **作用**: 遍历所有模板图片，按多个缩放比预生成缩放后图像，序列化到磁盘 pickle 文件。
- **实现**: 1. `get_template_meta` 列出所有图；2. 调 `get_scales_to_try(fast_mode=False)` 获得完整缩放列表；3. `cv2.resize` 批量生成；4. `pickle.dump` 写文件，`json.dump` 写 meta。
- **关键参数**: 无（缩放比由 `get_scales_to_try` 决定）。
- **复用价值**: 低 — 启动时自动调用，一般不手动触发。

### `load_template_file_cache(self)` — image_matcher.py:151
- **作用**: 从磁盘 pickle 文件加载预计算好的缩放模板到 `self.file_template_cache`。
- **实现**: `pickle.load` 反序列化，失败则初始化为空字典。
- **关键参数**: 无。
- **复用价值**: 低 — 内部基础设施。

### `prepare_template_cache(self)` — image_matcher.py:162
- **作用**: 启动时统一决策：缓存有效则加载，无效则重建后加载。
- **实现**: 1. `is_template_cache_valid` 检查；2. 无效时调 `build_template_file_cache`；3. 最后 `load_template_file_cache`。
- **关键参数**: 无。
- **复用价值**: 中 — bot 初始化时应调用一次，之后无需关心缓存层。

---

## 分组：截图与尺度工具

### `capture_region(self, region=None, mask_areas=None)` — image_matcher.py:175
- **作用**: 截取指定区域屏幕（或全屏），可选在指定矩形块上打黑，返回 BGR ndarray。
- **实现**: 1. `ImageGrab.grab(bbox, all_screens=True)`，失败降级 `pyautogui.screenshot`；2. `cv2.cvtColor(RGB→BGR)`；3. 对 `mask_areas` 中每个矩形填黑（用于遮挡已匹配目标）。
- **关键参数**: `region=(x,y,w,h)`；`mask_areas=[(x1,y1,x2,y2),...]`。
- **复用价值**: 高 — 所有匹配函数的截图基础，任何新流程都需要它。

### `get_scales_to_try(self, fast_mode=True)` — image_matcher.py:204
- **作用**: 根据当前屏幕宽度动态计算应尝试的缩放比列表，优先匹配 2560px 基准。
- **实现**: 1. 从 `self.regions["全界面"]` 获取当前宽度；2. 围绕主基准 2560 生成 ±2%/5%/8% 系列；3. 兼容 1920/1600 基准；4. 追加兜底比例；`fast_mode=True` 只取前 8 个。
- **关键参数**: `fast_mode=True`（快：8 个缩放；False：20+ 个缩放）。
- **复用价值**: 高 — 任何需要多尺度搜索的自定义匹配都应调用此函数获得缩放列表。

### `get_scaled_template(self, template_path, scale)` — image_matcher.py:236
- **作用**: 三级缓存查找（内存字典 → file_template_cache → 实时 resize）返回指定缩放比的模板。
- **实现**: 1. 查 `scaled_template_cache`（key=`(path, scale)`）；2. 查 `file_template_cache`（rel_key + scale_str）；3. 均未命中则 load + `cv2.resize` + 写入内存缓存。
- **关键参数**: `scale`（float）。
- **复用价值**: 高 — 所有多尺度匹配的模板获取统一入口，避免重复 IO 和 resize。

---

## 分组：基础彩色匹配

### `find_image_in_screen(self, screen_bgr, template_path, region=None, threshold=0.75, fast_mode=True)` — image_matcher.py:274
- **作用**: 在已有的 BGR 截图 ndarray 中查找单张模板，返回匹配中心坐标。
- **实现**: 1. `get_scales_to_try` 获取缩放列表；2. 每个 scale 调 `get_scaled_template`；3. `cv2.matchTemplate(TM_CCOEFF_NORMED)`；4. `minMaxLoc` 取最大值，≥threshold 即返回。
- **关键参数**: `threshold=0.75`；`fast_mode=True`。
- **复用价值**: 高 — 复用截图时的批量查找场景（避免重复截图）。

### `find_image(self, template_path, region=None, threshold=0.75, fast_mode=True)` — image_matcher.py:308
- **作用**: 最常用的单图查找入口：自动截图 + 调 `find_image_in_screen`。
- **实现**: 1. 检查 `is_running`；2. `capture_region(region)`；3. 转发 `find_image_in_screen`。
- **关键参数**: `threshold=0.75`；`fast_mode=True`。
- **复用价值**: 高 — 新流程查找任意 UI 按钮/状态图的首选函数。

### `find_any_image(self, image_list, region=None, threshold=MATCH_THRESHOLD, fast_mode=True)` — image_matcher.py:325
- **作用**: 截图一次，顺序尝试列表中每张图，找到任意一张就返回位置。
- **实现**: 截图 → 遍历 `image_list` → 逐一调 `find_image_in_screen`，首次命中即返回。
- **关键参数**: `threshold=0.8`（`MATCH_THRESHOLD` 常量）；`image_list`。
- **复用价值**: 高 — 多状态 UI 检测（如"确认"/"取消"同时搜索）的标准方式。

### `find_image_smart(self, template_path, primary_region=None, fallback_region=None, threshold=0.75, fast_mode=True)` — image_matcher.py:1504
- **作用**: 先在主区域查找，未找到再在备用区域查找的两步降级搜索。
- **实现**: 1. 若 `primary_region` 不为 None 则调 `find_image`；2. 失败则用 `fallback_region` 重试。
- **关键参数**: `primary_region`、`fallback_region`（均可为 None）。
- **复用价值**: 中 — 适合 UI 位置可能漂移到不同区域的场景。

---

## 分组：wait_for 轮询包装（彩色）

### `wait_for_image(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None)` — image_matcher.py:1816
- **作用**: 单图带超时轮询版 `find_image`，是 `wait_for_any_image` 的单图封装。
- **实现**: 转调 `wait_for_any_image([template_path], ...)`。
- **关键参数**: `timeout=30`；`interval=0.4`；`log_text` 每轮打印的等待日志。
- **复用价值**: 高 — 等待按钮/弹窗出现的最常用阻塞原语。

### `wait_for_any_image(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None)` — image_matcher.py:1788
- **作用**: 多图带超时轮询，每轮截图一次并顺序尝试所有候选图。
- **实现**: `while is_running and 未超时` → `capture_region` → `find_image_in_screen` × N；内层 sleep 粒度 0.05s 保证可响应中断。
- **关键参数**: `timeout=30`；`interval=0.4`；`log_text`。
- **复用价值**: 高 — 多状态等待的标准方式，替代硬编码 `time.sleep`。

### `wait_for_buy_and_used_car(self, timeout=20)` — image_matcher.py:1827
- **作用**: 专门等待"购买与二手车"界面出现，组合三种策略（灰度左侧/彩色全屏/彩色快速）。
- **实现**: 依次尝试 `wait_for_any_image_gray`（左区域）→ `wait_for_any_image`（全界面）→ `wait_for_any_image`（左区域 fast）。
- **关键参数**: `timeout=20`。
- **复用价值**: 低 — 业务专用，模式可参考用于其他"多策略降级"场景。

---

## 分组：二阶组合匹配（主图 + 子图）

### `find_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, fast_mode=True)` — image_matcher.py:346
- **作用**: 彩色二阶匹配：全屏找主图所有候选点，再在每个主图 ROI 周边 ±5px 内找子图。
- **实现**: 1. 多尺度 `get_scaled_template`；2. `matchTemplate` 全屏找主图，`np.where ≥ threshold`；3. 坐标去重（10px 格）；4. 提取 `[y-5:y+h+5, x-5:x+w+5]` ROI；5. 在 ROI 内再次 `matchTemplate` 找子图。
- **关键参数**: `threshold=0.85`（主/子共用）；`fast_mode=True`。
- **复用价值**: 高 — 需要"主图+附属标签"同时出现才点击时使用。

### `find_image_with_element_stable(self, main_path, sub_path, region=None, main_threshold=0.60, verify_threshold=0.72, sub_threshold=0.70, max_candidates=15)` — image_matcher.py:394
- **作用**: 灰度稳定版二阶匹配：取 top-N 候选点排序后验证，主图/子图阈值独立可调。
- **实现**: 1. `pyautogui.screenshot` + 灰度转换；2. `load_template_gray` 获取灰度模板；3. `matchTemplate ≥ main_threshold` 取所有点，按分数排序前 `max_candidates` 个；4. 每个候选用 `verify_threshold` 二次确认 + 子图 `sub_threshold` 验证。
- **关键参数**: `main_threshold=0.60`；`verify_threshold=0.72`；`sub_threshold=0.70`；`max_candidates=15`。
- **复用价值**: 中 — 主图模板较通用但需配合子图排除误判的场景。

### `find_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True, main_threshold=0.60, like_threshold=0.75, final_threshold=0.72, mask_areas=None)` — image_matcher.py:473
- **作用**: 五维评分二阶组合匹配：彩色 + 灰度 + 边缘 + 中心区 + 子图标签，抗 HDR 核心算法。
- **实现**: 1. 截图后生成 `screen_gray`、`screen_edge`；2. 多尺度取彩色 top-80 候选；3. 每个候选提取 ROI，计算 color/gray/edge/center/like 五个分数；4. `like_score < like_threshold` 则跳过；5. 加权综合分 ≥ `final_threshold` 即返回。权重：彩色 0.30 + 灰度 0.20 + 边缘 0.20 + 中心 0.15 + 标签 0.15。
- **关键参数**: `main_threshold=0.60`；`like_threshold=0.75`；`final_threshold=0.72`；`mask_areas`。
- **复用价值**: 高 — 最强匹配器，专用于"主卡片+NEW/like标签"组合场景，可直接复用于类似卡片界面。

### `find_image_with_element_fast(self, main_path, sub_path, region=None, threshold=0.70, sub_threshold=0.70)` — image_matcher.py:588
- **作用**: 灰度快速版二阶匹配，不做排序，顺序遍历所有候选点。
- **实现**: `pyautogui.screenshot` 灰度 → `matchTemplate ≥ threshold` → 遍历去重 → 子图 ROI 验证 `≥ sub_threshold`。
- **关键参数**: `threshold=0.70`；`sub_threshold=0.70`。
- **复用价值**: 中 — 速度优先、精度要求略低的二阶场景。

### `wait_for_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, timeout=30, interval=0.4, fast_mode=True)` — image_matcher.py:1842
- **作用**: `find_image_with_element` 的超时轮询包装。
- **实现**: `while is_running and 未超时` → 调 `find_image_with_element`；内层 0.05s 粒度 sleep。
- **关键参数**: `timeout=30`；`interval=0.4`。
- **复用价值**: 高 — 等待带附属元素的 UI 目标出现。

### `wait_for_image_with_element_stable(self, main_path, sub_path, region=None, main_threshold=0.60, verify_threshold=0.72, sub_threshold=0.70, max_candidates=15, timeout=3, interval=0.2)` — image_matcher.py:979
- **作用**: `find_image_with_element_stable` 的超时轮询包装。
- **实现**: 标准 `while` 轮询模式，`interval=0.2` 默认较短。
- **关键参数**: `timeout=3`；`interval=0.2`；其余同 find 版。
- **复用价值**: 中。

### `wait_for_image_with_element_fast(self, main_path, sub_path, region=None, threshold=0.70, sub_threshold=0.70, timeout=4, interval=0.25)` — image_matcher.py:1006
- **作用**: `find_image_with_element_fast` 的超时轮询包装。
- **实现**: 标准轮询，`timeout=4`，`interval=0.25`。
- **关键参数**: `timeout=4`；`interval=0.25`。
- **复用价值**: 中。

### `wait_for_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True, main_threshold=0.60, like_threshold=0.75, final_threshold=0.72, timeout=30, interval=0.4)` — image_matcher.py:652
- **作用**: `find_image_with_element_multi` 的超时轮询包装。
- **实现**: 标准轮询，内层 0.05s 粒度 sleep。
- **关键参数**: `timeout=30`；`interval=0.4`。
- **复用价值**: 高 — 等待刷图车卡片或其他带标签卡片出现的首选。

---

## 分组：灰度匹配

### `find_image_gray(self, template_path, region=None, threshold=0.75, fast_mode=True, invert_mode=False)` — image_matcher.py:1528
- **作用**: 纯灰度单图多尺度匹配，支持翻转模式（同时匹配原图和反相图）。
- **实现**: 1. `capture_region` → `cvtColor(BGR2GRAY)`；2. `load_template_gray` 读模板；3. 多尺度 `resize` + `matchTemplate`；4. `invert_mode=True` 时额外用 `255-tpl` 再匹配一次。
- **关键参数**: `threshold=0.75`；`invert_mode=False`；`fast_mode=True`。
- **复用价值**: 高 — 黑白 UI 元素（文字标签、图标）匹配、抗 HDR 干扰的首选。

### `find_any_image_gray(self, image_list, region=None, threshold=0.75, fast_mode=True, invert_mode=False)` — image_matcher.py:1594
- **作用**: 灰度多图版：截图一次，顺序尝试列表中每张灰度图，支持翻转模式。
- **实现**: `capture_region` → 灰度 → 对每张图多尺度匹配（+ 反相）。
- **关键参数**: `threshold=0.75`；`invert_mode=False`。
- **复用价值**: 高 — 多状态灰度 UI 检测（如白色/黑色切换标签）。

### `wait_for_image_gray(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False)` — image_matcher.py:1695
- **作用**: `find_image_gray` 的超时轮询包装。
- **实现**: 标准轮询，内层 0.05s 粒度 sleep 保证可中断。
- **关键参数**: `timeout=30`；`interval=0.3`。
- **复用价值**: 高 — 等待灰度 UI 元素出现（如上车按钮、品牌标志）。

### `wait_for_any_image_gray(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False)` — image_matcher.py:1662
- **作用**: `find_any_image_gray` 的超时轮询包装。
- **实现**: 标准轮询，内层 0.05s 粒度 sleep。
- **关键参数**: `timeout=30`；`interval=0.3`。
- **复用价值**: 高 — 多状态灰度等待。

---

## 分组：透明通道匹配

### `find_image_transparent(self, template_path, region=None, threshold=0.70, fast_mode=True)` — image_matcher.py:930
- **作用**: 利用 OpenCV `mask` 参数彻底无视模板透明区域，只匹配主体内容。
- **实现**: 1. `load_template_transparent` 获取 BGRA；2. 无 Alpha 则降级普通匹配；3. 多尺度 `resize`；4. 分离 BGR + Alpha → `cv2.matchTemplate(..., mask=alpha_mask)`。
- **关键参数**: `threshold=0.70`；`fast_mode=True`。
- **复用价值**: 高 — 模板有透明背景（PNG with alpha）时的首选，避免背景干扰。

### `find_any_image_transparent(self, image_list, region=None, threshold=0.70, fast_mode=True)` — image_matcher.py:1729
- **作用**: 截图一次，顺序尝试多张透明图，无 Alpha 的自动降级。
- **实现**: `capture_region` → 对每张图获取 BGRA → 多尺度 alpha-masked matchTemplate。
- **关键参数**: `threshold=0.70`；`image_list`。
- **复用价值**: 中 — 多张透明模板候选场景。

### `wait_for_image_transparent(self, template_path, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True)` — image_matcher.py:970
- **作用**: `find_image_transparent` 的超时轮询包装。
- **实现**: 标准轮询，`time.sleep(interval)` 简单阻塞（无内层粒度 sleep）。
- **关键参数**: `timeout=30`；`interval=0.4`。
- **复用价值**: 中。

### `wait_for_any_image_transparent(self, image_list, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True)` — image_matcher.py:1776
- **作用**: `find_any_image_transparent` 的超时轮询包装。
- **实现**: 内层 0.05s 粒度 sleep 保证可中断。
- **关键参数**: `timeout=30`；`interval=0.4`。
- **复用价值**: 中。

---

## 分组：终极安全锁 V5.1

### `find_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, mask_areas=None)` — image_matcher.py:1036
- **作用**: 三道防线的高精度匹配：① 排他图校验（anti）② 顶部 25% 文字区验证 ③ 右下角 25%×35% 调校区验证，全部通过才命中。
- **实现**: 1. 彩色初筛 `≥ main_threshold`；2. 按 X 坐标从左到右排序；3. 防线 1：在候选 ±10px ROI 内查 `anti_path`，分数 `≥ anti_threshold` 则排除；4. 防线 2：提取顶部模板核心（去 5px 边框）在 ROI 顶部 35% 内匹配；5. 防线 3：提取右下角模板在 ROI 对应区域匹配；三者同时满足阈值才返回。
- **关键参数**: `anti_path`（排除图）；`main_threshold=0.80`；`anti_threshold=0.65`；`mask_areas`。
- **复用价值**: 高 — 高误识别风险场景（如多张相似车牌/卡片）的安全保险。

### `wait_for_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, timeout=3, interval=0.2, mask_areas=None)` — image_matcher.py:1141
- **作用**: `find_image_ultimate_safe` 的超时轮询包装。
- **实现**: 标准 `while` 轮询，`time.sleep(interval)` 简单阻塞。
- **关键参数**: `timeout=3`；`interval=0.2`。
- **复用价值**: 高 — 安全锁的等待版本。

---

## 分组：颜色辅助 + 新标签检测

### `find_new_tag_by_color(self, screen_bgr, tag_tpl, scale)` — image_matcher.py:1149
- **作用**: 通过 HSV 黄色掩码筛选"全新"标签候选区域，再模板验证，返回卡片中心坐标候选列表。
- **实现**: 1. BGR→HSV；2. `inRange([22,80,160],[42,255,255])` 提取黄色区域；3. `morphologyEx CLOSE` 去噪；4. `findContours` 找轮廓，过滤面积/宽高比；5. 对每个轮廓提取 pad 后 ROI 做 `match_template_score`；6. 推算卡片中心并收集候选。
- **关键参数**: `screen_bgr`（已截图）；`tag_tpl`（已加载模板）；`scale`。
- **复用价值**: 中 — 颜色预筛 + 模板验证管道的参考实现，可复用于其他带特定色标签的场景。

### `validate_new_tag_grid_fallback(self, screen_bgr, tx, ty, tw, th)` — image_matcher.py:1202
- **作用**: 对"全新"标签候选坐标做网格结构验证：左上方需有白色车辆卡片，左下方需有橙色等级条。
- **实现**: 1. 位置范围检查（非边缘）；2. 左上 ROI 计算白色像素比例 `≥ 0.18`；3. 左下 ROI 提取 HSV 橙色比例 `≥ 0.035`；均满足则返回点击坐标。
- **关键参数**: `tx,ty,tw,th`（标签位置和尺寸）。
- **复用价值**: 低 — 新车检测内部辅助函数。

---

## 分组：严格新消耗车检测

### `find_new_consumable_car_strict(self, region=None, save_miss=False)` — image_matcher.py:1246
- **作用**: 三锚点严格检测：全新标签 + B600 等级 + 车辆卡片主体同时满足位置关系和多部位分数才命中。
- **实现**: 1. 多尺度（优先 1.0/0.98/1.02）加载三个模板：`newCC.png`/`newcartag.png`/`classB600.png`；2. 以 `newcartag` 为锚找候选；3. 验证 1：`classB600` 须在标签下方一定范围内；4. 验证 2：`newCC` 须在标签左上角附近，相对位置约束 `[0.62w,1.08w] × [0.55h,1.08h]`；5. 验证 3：顶部 24% 车名区分数 `≥ 0.72`；6. 验证 4：右下角 25%×35% 分数 `≥ 0.72`；全部通过返回卡片中心。`save_miss=True` 时调 `save_strict_car_debug` 存调试图（该函数定义在其他 mixin）。
- **关键参数**: `region`；`save_miss=False`。
- **复用价值**: 高 — 超抽流程中识别新消耗车的核心算法，可模仿结构适配其他多标签卡片。

### `wait_for_new_consumable_car_strict(self, timeout=3, interval=0.2)` — image_matcher.py:1466
- **作用**: 综合调度：根据 `config` 中 `ai_assist`/`ai_prefer`/`ai_only` 标志决定调 AI 还是严格算法，并按优先级组合。
- **实现**: 1. `ai_first` 时先调 `find_new_consumable_car_ai`（外部 mixin）；2. 轮询 `find_new_consumable_car_strict`；3. 轮询结束后若仍未找到且 `ai_enabled` 则再调 AI；4. 最后兜底一次 strict（附 `save_miss`）。
- **关键参数**: `timeout=3`；`interval=0.2`；依赖 `config["ai_assist"]`/`"ai_prefer"`/`"ai_only"`/`"ai_auto_capture"`。
- **复用价值**: 中 — 调度模式可参考，直接复用需要同步 AI mixin。

---

## 分组：刷图车（SkillCar）专用

### `find_skill_car_with_like_tag(self, region=None, timeout=3.0, interval=0.25)` — image_matcher.py:676
- **作用**: 在 timeout 内轮询两种策略找带 liketag 的刷图车：`find_image_with_element_multi` + `find_skill_car_from_like_tag`。
- **实现**: `while` 轮询，依次调两个查找函数，任一命中即返回。
- **关键参数**: `timeout=3.0`；`interval=0.25`。
- **复用价值**: 中 — 刷图车专用，但双策略轮询模式可作参考。

### `find_skill_car_from_like_tag(self, region=None)` — image_matcher.py:698
- **作用**: 反向策略：先找 liketag，再从 tag 位置向左上方搜索 skillcar 主体，验证相对位置合理性。
- **实现**: 1. 多尺度加载 `skillcar.png`/`liketag.png`；2. `matchTemplate ≥ 0.66` 找所有 tag 候选；3. 每个 tag 向左右扩展搜索 car 区域；4. `cv2.matchTemplate` 找 car，验证 `rel_x`/`rel_y` 在允许范围 ±8%；5. `car_score ≥ 0.64` 才返回。
- **关键参数**: 阈值均硬编码（tag=0.66，car=0.64）。
- **复用价值**: 中 — 反向锚点搜索模式（先小标签后大主体）可复用于类似布局。

### `should_switch_skillcar_after_cj(self)` — image_matcher.py:768
- **作用**: 读取 UI 控件或 config，判断超抽后是否需要切换刷图车。
- **实现**: 优先读 `self.var_chk3.get()` 和 `self.entry_next3.get()`，失败降级读 `self.config`。
- **关键参数**: 无。
- **复用价值**: 低 — 业务状态查询，高度耦合 UI。

### `switch_to_liked_skillcar_in_car_list(self)` — image_matcher.py:774
- **作用**: 在车辆列表界面循环右移，找到带 liketag 的刷图车并点击上车，最后按 Tab 返回漫游。
- **实现**: 最多循环 30 次：方向键右移 × 4 → `find_skill_car_with_like_tag` 查找；找到后 `game_click` → 等待 `rc.png`（上车按钮）→ `hw_press("tab")`。
- **关键参数**: `self.regions["全界面"]`。
- **复用价值**: 低 — 高度业务耦合。

### `prepare_skillcar_for_next_race_after_cj(self)` — image_matcher.py:825
- **作用**: 超抽后切换刷图车的完整流程：进入我的车辆 → 上移找斯巴鲁品牌 → 切换至带 liketag 刷图车。
- **实现**: 1. `enter_my_cars_from_vehicle_menu`；2. Backspace 重置；3. 循环上移 + `wait_for_image_gray("skillcarbrand.png")`；4. 点击品牌 → `switch_to_liked_skillcar_in_car_list`。
- **关键参数**: 无（内部使用 `self.regions["全界面"]`）。
- **复用价值**: 低 — 业务专用。

### `enter_my_cars_from_vehicle_menu(self)` — image_matcher.py:861
- **作用**: 从车辆菜单导航至"我的车辆"：确认当前菜单状态后用方向键上移 + 回车进入。
- **实现**: 12 次重试找 `UandT-w.png`/`UandT-b.png` → 连按 up×6 → `hw_press("enter")`。
- **关键参数**: 无。
- **复用价值**: 低 — 业务导航专用。

### `return_to_vehicle_menu_after_mastery(self)` — image_matcher.py:892
- **作用**: 从精通/调校子菜单用 Esc×2 退出，确认回到车辆菜单。
- **实现**: `hw_press("esc")×2` → 轮询 `find_any_image_gray(["UandT-w.png","UandT-b.png"])` 最多 8 次。
- **关键参数**: 无。
- **复用价值**: 低 — 业务导航专用。

---

## 分组：图像处理工具

### `to_gray_image(self, img)` — image_matcher.py:1514
- **作用**: BGR ndarray 转灰度图的一行封装。
- **实现**: `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`。
- **关键参数**: `img`（BGR ndarray）。
- **复用价值**: 中 — 在自定义匹配管道中复用。

### `to_edge_image(self, img)` — image_matcher.py:1516
- **作用**: BGR ndarray 转 Canny 边缘图（GaussianBlur + Canny 50/150）。
- **实现**: 灰度 → `GaussianBlur(3,3,0)` → `Canny(50,150)`。
- **关键参数**: `img`（BGR ndarray）。
- **复用价值**: 中 — 边缘特征匹配预处理。

### `crop_center_ratio(self, img, ratio=0.6)` — image_matcher.py:1521
- **作用**: 按比例裁剪图像中心区域。
- **实现**: 计算 `ch=h*ratio, cw=w*ratio`，从中心偏移裁剪。
- **关键参数**: `ratio=0.6`（裁剪比例）。
- **复用价值**: 中 — 在 `find_image_with_element_multi` 中用于中心区加权评分，可独立复用于图像对比。

### `match_template_score(self, src, tpl)` — image_matcher.py:1862
- **作用**: 对任意 src/tpl（同通道）做一次 `TM_CCOEFF_NORMED` 匹配，返回最大分数 float。
- **实现**: 尺寸合法性检查 → `matchTemplate` → `minMaxLoc()[1]`；异常返回 0.0。
- **关键参数**: `src`、`tpl`（ndarray，需相同通道数）。
- **复用价值**: 高 — 嵌入自定义评分管道的原子打分函数，`find_image_with_element_multi` 五维评分全部依赖它。

---

## 分组：测试线束（F3）

### `start_test_find_image(self)` — image_matcher.py:1877
- **作用**: F3 键触发的测试模式：在 `全界面` 区域反复调 `find_image_with_element_multi` 最多找 15 次目标，只移动鼠标不点击，已找到的区域用 mask 遮挡防重复。
- **实现**: 1. 检查 `is_running` 防止重复启动；2. 启动 daemon 线程 `test_runner`；3. 调 `check_and_focus_game`；4. 循环 15 次：`find_image_with_element_multi(mask_areas=...)` → `hw_mouse_move` → 累加遮罩；5. 结束后 `stop_all`。
- **关键参数**: 模板硬编码 `newCC.png`/`newcartag.png`；阈值均 0.70。
- **复用价值**: 低 — 调试专用，可作为"多目标顺序扫描 + 遮罩去重"模式的参考实现。

---

*注：`find_new_consumable_car_ai` 和 `save_strict_car_debug` 在本文件中被调用但定义在其他 Mixin（AI 识别模块），不在本清单内。*


---

# main.py 1–1520 — 初始化/配置/输入/区域/AI

# main.py 函数清单（行 1–1520）

## 总览(1-1520)

这个范围涵盖整个模块的顶层骨架：导入/环境检测、ctypes 硬件输入结构体、DIK_CODES 扫描码字典、GUI 类 `FH_UltimateBot` 的构造与全部基础层方法（配置、UI 调度、硬件输入、区域管理、YOLO/AI 选车、调试图保存、暂停机制、热键监听、游戏焦点管理）。流程入口 `start_pipeline` 与 `stop_all` 也在此范围内，是整个机器人运行的顶层驱动。

**最可复用的辅助函数**：
- `hw_key_down / hw_key_up` — 基于 SendInput 扫描码的底层按键注入（游戏防检测）
- `hw_press` — 一键按下+延迟+弹起，内嵌暂停拦截
- `hw_mouse_move` — 多显示器虚拟桌面坐标系的硬件级鼠标移动
- `game_click` — 焦点校验 + 硬件移动 + 点击 + 防悬浮偏移的完整点击原子操作
- `load_config / save_config` — JSON 配置的底本合并读写
- `update_regions_by_window` — 动态计算 11 个游戏区域矩形
- `check_pause` — 阻塞型暂停门卫（所有动作前调用）
- `find_new_consumable_car_ai` — YOLO 推理 → 候选评分 → 返回点击坐标的完整 AI 选车入口
- `ensure_game_focus` — 任意操作前的游戏焦点守卫，自动恢复

---

## 模块级

| 位置 | 名称/结构 | 说明 |
|------|-----------|------|
| 1–9 | imports 顶层 | sys/os/json/time/ctypes/subprocess 等标准库 |
| 11–36 | `check_windows_dependencies()` 模块级函数 | 启动前 DLL 检测，见下方函数表 |
| 39–45 | DPI 感知设置 | `SetProcessDpiAwareness(2)` 等模块顶层执行 |
| 47–77 | 第三方库导入 | ctk/cv2/np/pyautogui/pydirectinput/pynput/win32gui/threading + 项目内部模块 |
| 80–81 | `SendInput`, `PUL` | ctypes 全局句柄 |
| 84–125 | `KeyBdInput`, `HardwareInput`, `MouseInput`, `Input_I`, `Input` | ctypes 结构体，SendInput 所需 |
| 129–209 | **`DIK_CODES`** | 硬件扫描码字典，覆盖 Esc/Enter/Space/Shift/Ctrl/Alt/CapsLock + a-z + 0-9 + 方向键/PgUp/PgDn/Home/End/Ins/Del + F1-F12，格式 `key -> (scan_code, extended_bool)` |
| 212–214 | 全局 CTK / pyautogui 设置 | Dark 模式、FAILSAFE=False |

---

## 分组：启动前环境检测

### `check_windows_dependencies()` — main.py:11
- **作用**: 启动时检测 VC++ 运行库是否存在，缺失则弹窗警告
- **实现**:
  1. 仅在 win32 上运行
  2. 依次 `ctypes.WinDLL()` 尝试加载 vcruntime140.dll / msvcp140.dll / vcruntime140_1.dll
  3. 收集缺失列表，用 `MessageBoxW` 展示中文警告
- **复用价值**: 中 — 任何需要 VC++ 依赖的 Python Windows 桌面程序都可直接复用

---

## 分组：GUI 类 FH_UltimateBot — 构造与初始化

### `__init__(self)` — main.py:218
- **作用**: 构建整个 bot 实例，初始化窗口属性、全部状态字段、模板缓存、线程、后台加载
- **实现**:
  1. 调用父类 `super().__init__()` 并配置窗口尺寸/透明度/图标
  2. 初始化所有运行状态字段（计数器、缓存字典、YOLO 字段、游戏焦点字段等）
  3. `init_regions()` → 后台线程执行 `auto_extract_images()` + `prepare_template_cache()`
  4. `load_config()` → `setup_ui()` → `start_hotkey_listener()` → `update_skill_grid()` → `center_window()` → `preload_ai_model_async()`
- **复用价值**: 低 — 高度特化于本 bot，但初始化模式（后台加载 + 懒加载模型）可借鉴

---

## 分组：UI 安全调度

### `ui_call(self, func, *args, **kwargs)` — main.py:309
- **作用**: 将 UI 更新操作安全派发到主线程（`self.after(0, ...)`）
- **实现**:
  1. `self.after(0, lambda: func(*args, **kwargs))` 包 try/except
- **复用价值**: 高 — 所有从子线程更新 tkinter/ctk 控件的通用模式

### `center_window(self)` — main.py:315
- **作用**: 将窗口居中显示在游戏所在显示器上
- **实现**:
  1. `update_idletasks()` 获取实际窗口尺寸
  2. 从 `regions["全界面"]` 获取游戏区域
  3. 计算居中坐标并 `geometry()` 设置
- **复用价值**: 中 — 多显示器环境下按目标区域居中窗口的通用方法

### `format_elapsed(self, seconds)` — main.py:324
- **作用**: 将秒数格式化为 `HH:MM:SS` 字符串
- **实现**: 简单整除 + `f"{hrs:02d}:{mins:02d}:{secs:02d}"`
- **复用价值**: 高 — 纯工具函数，无依赖，直接复制即用

### `reset_run_stats(self)` — main.py:331
- **作用**: 重置任务开始时间与各子任务累计时间字典
- **实现**:
  1. `self.start_time = time.time()`
  2. 初始化 `active_task_name`、`active_task_started_at`、`task_time_totals` 字典
- **复用价值**: 低 — 绑定本 bot 任务结构

### `finalize_active_task_time(self)` — main.py:343
- **作用**: 将当前活跃任务的已用时间累加到对应桶中，并更新起始时间戳
- **实现**:
  1. 取 `active_task_name` / `active_task_started_at`
  2. 若任务名在 `task_time_totals` 中则累加差值
  3. 更新 `active_task_started_at = time.time()`
- **复用价值**: 低 — 专用于本 bot 的分任务计时

### `normalize_step_entry(self, entry_widget, default_value)` — main.py:350
- **作用**: 规范化步骤输入框的值（只允许 1-3 的整数，非法时恢复默认）
- **实现**:
  1. 提取输入框内容中的数字字符
  2. 强制 clamp 到 [1, 3]
  3. 写回输入框
- **复用价值**: 中 — 通用 Entry 数值规范化模式

---

## 分组：初始化全局 Region

### `init_regions(self)` — main.py:368
- **作用**: 用全屏尺寸初始化 `regions` 字典（启动时默认值）
- **实现**:
  1. `pyautogui.size()` 获取屏幕尺寸
  2. 调用 `update_regions_by_window(0, 0, sw, sh)`
- **复用价值**: 低 — 触发器；实质逻辑在 `update_regions_by_window`

### `update_regions_by_window(self, x, y, w, h)` — main.py:372
- **作用**: 根据游戏窗口矩形动态计算全部 11 个命名截图区域
- **实现**:
  1. 构建 `self.regions` 字典，key 为中文区域名
  2. 覆盖：全界面/左上/右上/左下/右下/上/下/左/右/中间/车辆菜单列表
  3. 车辆菜单列表使用百分比偏移（h*0.48、w*0.26、h*0.42）
- **复用价值**: 高 — 所有基于窗口相对坐标的截图区域计算都可参考此模式

---

## 分组：配置管理

### `load_config(self)` — main.py:395
- **作用**: 加载配置，内置底本字典 + 读取 USER_CONFIG_FILE JSON 合并 + 写回
- **实现**:
  1. 硬编码默认 config 字典（race_count/buy_count/skill_dirs/ai_assist 等 ~20 字段）
  2. `self.config.update(gift_default_config())` 合并礼品模块默认值
  3. 若 JSON 文件存在则 `update()` 覆盖；文件损坏则记录日志
  4. 将合并后完整配置写回 JSON 文件（补全缺失键）
- **复用价值**: 高 — "底本+用户覆盖+写回" 配置管理模式通用

### `save_config(self)` — main.py:441
- **作用**: 从 UI 控件读取当前值并写回 config 字典及 JSON 文件
- **实现**:
  1. 读取各 entry 控件（race/buy/cj/timeout/share_code/next1-3 等）
  2. 读取 checkbox var（chk1-3/ai_assist/ai_only/smart_page 等）
  3. `json.dump` 写回 USER_CONFIG_FILE
- **复用价值**: 中 — GUI 配置序列化的标准模式

---

## 分组：UI 布局设计

### `setup_ui(self)` — main.py:483
- **作用**: 委托 `ui_layout.setup_ui(self)` 构建全部 GUI 控件
- **实现**: 单行调用，将 self 注入外部布局模块
- **复用价值**: 低 — 委托模式，实质在 ui_layout.py

### `update_timer(self)` — main.py:487
- **作用**: 每秒刷新运行时面板上的总用时/当前任务用时/分任务累计用时标签
- **实现**:
  1. 计算 total_elapsed / task_elapsed
  2. 实时累加当前活跃任务到对应桶（race/buy/cj）
  3. 更新三个 lbl 控件文本
  4. `self.after(1000, self.update_timer)` 自循环
- **复用价值**: 中 — 自循环 `after` 定时更新 UI 的通用模式

### `update_running_ui(self, task_name="", current_val=0, max_val=0)` — main.py:522
- **作用**: 更新运行面板的当前任务名称和进度 "X / Y" 标签
- **实现**:
  1. 若 task_name 变化则调用 `finalize_active_task_time()` 并更新 `active_task_name`
  2. 用 `ui_call` 线程安全更新 lbl_runtime_task / lbl_runtime_progress
- **复用价值**: 中 — 线程安全的进度标签更新封装

### `update_running_state(self, state)` — main.py:535
- **作用**: 根据 running/paused/idle 三态刷新全部运行状态相关控件的外观
- **实现**:
  1. "running"：绿色状态标、启用暂停/停止按钮、更新按钮文字颜色
  2. "paused"：橙色状态标、暂停按钮变"继续 F9"
  3. 其他（idle）：重置全部标签/按钮到初始灰色待机状态
- **复用价值**: 中 — 多态 UI 状态机模式可复用

---

## 分组：核心操作与流程控制

### `hw_key_down(self, key)` — main.py:563
- **作用**: 通过 SendInput 扫描码发送键盘按下事件（底层硬件级，游戏防反作弊）
- **实现**:
  1. 查 `DIK_CODES[key]` 取扫描码和 extended 标志
  2. 设置 `KEYEVENTF_SCANCODE`（0x0008）flags，extended 加 `KEYEVENTF_EXTENDEDKEY`（0x0001）
  3. 构建 `Input` 结构体并调用 `SendInput`
  4. 先调用 `ensure_game_focus()` 确保窗口焦点
- **复用价值**: 高 — 任何需要硬件级键盘注入绕过 DirectInput 检测的场景

### `hw_key_up(self, key)` — main.py:576
- **作用**: 通过 SendInput 扫描码发送键盘弹起事件
- **实现**: 同 `hw_key_down`，flags 改为 `KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP`（0x000A）
- **复用价值**: 高 — 与 `hw_key_down` 成对使用

### `hw_press(self, key, delay=0.08)` — main.py:589
- **作用**: 原子按键操作：check_pause → down → sleep(delay) → up
- **实现**:
  1. `self.check_pause()` 暂停拦截
  2. `self.hw_key_down(key)`
  3. `time.sleep(delay)`
  4. `self.hw_key_up(key)`
- **复用价值**: 高 — 所有单次按键调用此方法即可，自带暂停门卫

### `parse_key_list(self, raw_value, default=None)` — main.py:597
- **作用**: 将字符串/列表形式的按键配置解析为有效 DIK_CODES 键名列表
- **实现**:
  1. 若 raw_value 已是列表直接使用
  2. 否则将多种分隔符（中文逗号/顿号/分号等）统一替换为逗号再 split
  3. 过滤不在 DIK_CODES 中的键名，去重，返回或兜底 default
- **复用价值**: 高 — 通用按键配置字符串解析器

### `get_drive_keys(self)` — main.py:617
- **作用**: 从 config 读取并解析驾驶按键列表
- **实现**: 调用 `parse_key_list(config["drive_keys"])` 并返回
- **复用价值**: 低 — 简单封装

### `set_drive_keys_down(self)` — main.py:620
- **作用**: 同时按下所有驾驶键（模拟加速）
- **实现**: 遍历 `get_drive_keys()` 依次调用 `hw_key_down`
- **复用价值**: 中 — 多键同时按下的通用封装

### `set_drive_keys_up(self)` — main.py:624
- **作用**: 同时松开所有驾驶键
- **实现**: 遍历 `get_drive_keys()` 依次调用 `hw_key_up`
- **复用价值**: 中 — 与 `set_drive_keys_down` 成对使用

### `hw_mouse_move(self, x, y)` — main.py:628
- **作用**: 硬件级多显示器兼容鼠标绝对移动（虚拟桌面坐标系）
- **实现**:
  1. 读取 SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CXVIRTUALSCREEN/SM_CYVIRTUALSCREEN
  2. 映射物理坐标到 0~65535 虚拟绝对坐标
  3. `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK` flags
  4. `SendInput` 发送 MouseInput 结构体
- **复用价值**: 高 — 副屏/多显示器环境下唯一可靠的鼠标绝对移动实现

### `game_click(self, pos, double=False)` — main.py:650
- **作用**: 完整的游戏点击原子操作：暂停拦截 → 焦点校验 → 移动 → 点击 → 复位鼠标
- **实现**:
  1. `check_pause()` + 运行状态检查 + `ensure_game_focus()`
  2. `hw_mouse_move(x, y)` + sleep(0.2)
  3. 单/双击：`pydirectinput.mouseDown()` + sleep(0.1) + `mouseUp()`
  4. 移回左上角安全位置防止悬浮提示遮挡
- **复用价值**: 高 — 游戏内所有 UI 点击的标准入口

### `move_to_game_coord(self, x, y)` — main.py:677
- **作用**: 将以游戏窗口左上角为原点的相对坐标转为绝对坐标并移动鼠标
- **实现**:
  1. 从 `regions["全界面"]` 取 gx/gy 偏移
  2. `hw_mouse_move(gx+x, gy+y)`，失败时直接用绝对坐标
- **复用价值**: 高 — 所有基于游戏内相对坐标的鼠标移动统一走这里

### `add_skill_dir(self, direction)` — main.py:691
- **作用**: 向 skill_dirs 列表追加一个方向并刷新 UI 网格和保存配置
- **实现**: append → `update_skill_grid()` → `save_config()`
- **复用价值**: 低 — 专用于技能方向编辑功能

### `clear_skill_dir(self)` — main.py:696
- **作用**: 清空 skill_dirs 并刷新 UI 网格
- **实现**: `.clear()` → `update_skill_grid()` → `save_config()`
- **复用价值**: 低 — 专用于技能方向编辑功能

### `update_skill_grid(self)` — main.py:701
- **作用**: 根据 skill_dirs 方向序列在 4×4 网格上高亮技能路径
- **实现**:
  1. 全部格子设为灰色 (#333333)
  2. 从起始格 (3,0) 按方向序列移动，边界内的格子染蓝色 (#3498DB)
  3. 越界则截断有效路径并更新 config
- **复用价值**: 低 — 专用于技能网格可视化

### `log(self, message)` — main.py:728
- **作用**: 线程安全地向日志文本框追加带时间戳的消息，超阈值自动截断
- **实现**:
  1. 格式化 `[HH:MM:SS] message`
  2. 内嵌 `write_ui()` 闭包：`configure(state=normal)` → insert → 计数 → 超 1200 行删至 800 → `see("end")` → disable
  3. `ui_call(write_ui)` 派发到主线程
- **复用价值**: 高 — 线程安全日志 + 自动滚动 + 行数限制的通用模式

### `toggle_log_panel(self)` — main.py:748
- **作用**: 折叠/展开底部日志面板，同时调整窗口最小尺寸和高度
- **实现**:
  1. 折叠：`bottom_frame.pack_forget()`，保存当前高度，缩减 minsize
  2. 展开：`bottom_frame.pack()`，恢复 minsize 和保存的高度
- **复用价值**: 低 — 日志面板折叠 UI 模式

### `write_debug_image(self, path, image_bgr)` — main.py:772
- **作用**: 将 BGR 图像安全写入指定路径（自动创建目录，处理中文路径）
- **实现**:
  1. `os.makedirs(dirname, exist_ok=True)`
  2. `cv2.imencode(".png", image_bgr)` → `buf.tofile(path)`（解决 cv2 不支持中文路径问题）
- **复用价值**: 高 — 跨平台/中文路径安全的 OpenCV 图像写入封装

### `on_ai_assist_changed(self)` — main.py:783
- **作用**: AI 辅助复选框变更回调，同步 config 并触发模型加载/卸载
- **实现**:
  1. 读取 `var_ai_assist` 状态
  2. 禁用时清空 YOLO 模型引用；启用时调 `preload_ai_model_async()`
  3. `save_config()` + `log()`
- **复用价值**: 低 — 绑定本 bot UI 逻辑

### `on_smart_page_changed(self)` — main.py:799
- **作用**: 智能翻页复选框变更回调，禁用时重置页码缓存
- **实现**: 读 var → 更新 config → 若禁用则 `memory_car_page = 0` → save/log
- **复用价值**: 低 — 绑定本 bot 功能

### `on_ai_only_changed(self)` — main.py:807
- **作用**: AI 纯模式复选框变更回调，启用时强制同步启用 ai_assist
- **实现**: 读 var → 若 enabled 则强制 ai_assist/ai_prefer 为 True → save/log
- **复用价值**: 低 — 绑定本 bot 功能

### `on_ai_auto_capture_changed(self)` — main.py:817
- **作用**: AI 自动截图保存复选框变更回调
- **实现**: 读 var → 更新 config → save/log
- **复用价值**: 低 — 绑定本 bot 功能

### `resolve_ai_model_path(self)` — main.py:823
- **作用**: 按优先级候选列表解析 YOLO 模型文件的绝对路径
- **实现**:
  1. 优先取 config 中的 ai_model_path
  2. 依次尝试 4 个候选路径（相对转绝对）
  3. 返回第一个 `os.path.exists()` 为真的路径，否则 None
- **复用价值**: 中 — 多路径候选解析模式可复用

### `get_yolo_car_select_model(self)` — main.py:844
- **作用**: 懒加载并缓存 YOLO 选车模型（线程安全）
- **实现**:
  1. `ai_assist` 关闭则返回 None
  2. 调 `resolve_ai_model_path()` 查找模型文件
  3. 加锁：若路径未变且已加载则返回缓存；否则 `YOLO(model_path)` 加载
- **复用价值**: 高 — 线程安全单例懒加载 ML 模型的通用模式

### `preload_ai_model_async(self)` — main.py:866
- **作用**: 异步后台预加载 YOLO 模型，避免首次调用阻塞
- **实现**:
  1. 若已预加载或 ai_assist 未启用则提前返回
  2. 启动 daemon 线程调 `get_yolo_car_select_model()`
- **复用价值**: 中 — 异步预加载重型模型的通用模式

### `resolve_ai_device(self)` — main.py:877
- **作用**: 自动检测最优推理设备（CUDA GPU 或 CPU）
- **实现**:
  1. 读 config ai_device（默认 "auto"）
  2. `torch.cuda.is_available()` 检测 GPU，auto 时返回 "0"
  3. 配置了 cpu/mps 则直接返回，否则兜底 cpu
- **复用价值**: 高 — 任何 YOLO/PyTorch 推理设备选择场景

### `yolo_box_to_dict(self, item, conf_threshold=0.25)` — main.py:889
- **作用**: 将 YOLO result.boxes 中的单个框转为结构化字典，低置信度过滤
- **实现**:
  1. 取 `item.conf[0]`，低于阈值返回 None
  2. 取 cls_id，映射到 {0:"new", 1:"b600", 2:"car"}
  3. 计算 xyxy/w/h/cx/cy 并打包返回字典
- **复用价值**: 高 — YOLO 框解析的通用工具，无 bot 特异依赖

### `yolo_yellow_tag_ratio(self, img, box)` — main.py:910
- **作用**: 计算 box 区域内黄色像素占比（用于验证"新车"标签颜色）
- **实现**:
  1. 切出 box ROI，转 HSV
  2. `cv2.inRange` 检测黄色范围 H=[24,42] S=[90,255] V=[170,255]
  3. 返回非零像素 / 总像素比值
- **复用价值**: 高 — 颜色占比检测的通用工具

### `yolo_box_distance(self, a, b)` — main.py:925
- **作用**: 计算两个 box 字典中心点欧氏距离
- **实现**: `np.hypot(a["cx"]-b["cx"], a["cy"]-b["cy"])`
- **复用价值**: 高 — 纯工具，任何需要比较 box 位置距离的场景

### `find_yolo_car_candidate(self, img, boxes, min_tag_yellow_ratio=0.18)` — main.py:928
- **作用**: 从 YOLO 检测到的所有框中用多规则评分找出最佳"可消耗新车"候选
- **实现**:
  1. 按 name 分离 tags(new)/classes(b600)/cars(car)
  2. 对每个 tag：检查位置约束、黄色比、寻找最近 B600 框、寻找关联 car 框
  3. 计算综合 score = tag*0.34 + b600*0.28 + car*0.38
  4. 按 (y1, x1, -score) 排序返回最佳候选和失败原因
- **复用价值**: 中 — 评分候选框的多约束筛选模式可参考，业务规则高度特异

### `save_ai_car_debug(self, screen_bgr, status, boxes=None, candidate=None, reason="", click=None, force=False)` — main.py:987
- **作用**: 保存 AI 选车的原始截图和标注图到 debug/car_select_ai 目录
- **实现**:
  1. miss 状态节流（1.5 秒内不重复保存）
  2. 写原始图 raw/
  3. 在 annotated 图上绘制所有框（颜色编码）、选中框（红色加粗）、点击十字、reason 文字
  4. 按 pass/miss 写入对应子目录
- **复用价值**: 中 — AI 调试图保存带标注的通用模式

### `find_new_consumable_car_ai(self, region=None, save_miss=True)` — main.py:1058
- **作用**: 完整的 AI 选车推理流程入口，返回绝对坐标点击位置或 None
- **实现**:
  1. `get_yolo_car_select_model()` 获取模型
  2. `capture_region(region)` 截图
  3. `model.predict()` 推理
  4. 遍历 result.boxes → `yolo_box_to_dict()` 过滤 → `find_yolo_car_candidate()` 筛选
  5. 成功则计算绝对坐标并可选保存调试图，返回 click_abs
- **复用价值**: 高 — AI 选车的顶层调用接口，外部只需调此方法

### `save_strict_car_debug(self, screen_bgr, status, reason="", boxes=None, scores=None, click=None, force=False)` — main.py:1110
- **作用**: 保存模板匹配选车的原始截图和标注图到 debug/car_select 目录
- **实现**:
  1. miss 状态节流（1.5 秒）
  2. pass 时调 `cleanup_recent_strict_car_miss()` 清理最近的误判 miss 图
  3. 写原始图；在 annotated 上绘制命名矩形框（color_map）、分数文字、点击标记、reason
  4. 按 pass/miss 写入子目录
- **复用价值**: 中 — 模板匹配调试可视化的通用模式

### `cleanup_recent_strict_car_miss(self, root, keep_seconds=12.0)` — main.py:1187
- **作用**: 删除 keep_seconds 秒内创建的 miss 调试图（成功识别后清理假阴性残留）
- **实现**:
  1. 遍历 miss/ 子目录中 .png 文件
  2. `os.path.getmtime()` 判断是否在 keep_seconds 内
  3. 删除 miss 图和对应 raw 图
- **复用价值**: 低 — 专用于 bot 调试图清理

### `start_pipeline(self, start_step)` — main.py:1211
- **作用**: 顶层任务驱动器：启动 race/buy/cj 按配置顺序循环的主线程
- **实现**:
  1. 首次 race 弹确认对话框
  2. 设置 `is_running=True`，重置所有计数器，启动定时器
  3. 内嵌 `runner()` 线程：`check_and_focus_game()` → while 循环调 `logic_race/logic_buy_car/logic_super_wheelspin`
  4. 失败时调 `attempt_recovery()`，连续失败超 MAX_RECOVERIES(10) 次则 break
  5. 成功后按 next_idx 逻辑推进步骤，global_loop_current 到达上限后退出
- **复用价值**: 低 — 高度特化于本 bot 的主循环驱动器，但步骤调度模式可参考

### `stop_all(self)` — main.py:1347
- **作用**: 强制停止所有任务，松开全部按键，重置 UI 到待机状态
- **实现**:
  1. `is_running=False`，`is_paused=False`
  2. 遍历 DIK_CODES 所有键 + 额外常用键发送 key_up
  3. `pydirectinput.mouseUp()`
  4. `finalize_active_task_time()` → `update_running_state("idle")`
- **复用价值**: 高 — 紧急停止/清理所有输入状态的通用安全模式

### `start_test_boot(self)` — main.py:1368
- **作用**: 独立运行自动开机识别测试流程（不进入主循环）
- **实现**:
  1. 检查 is_running
  2. 设置运行状态，后台线程调 `restart_game_and_boot(force_test=True)`
  3. 测试完成后自动 `stop_all()`
- **复用价值**: 低 — 专用测试入口

---

## 分组：暂停与恢复逻辑

### `toggle_pause(self)` — main.py:1396
- **作用**: 切换暂停/恢复状态，暂停时强制松开所有键/鼠标
- **实现**:
  1. `is_paused = not is_paused`
  2. 暂停：`set_drive_keys_up()` + 松开所有功能键 + `mouseUp()` + UI 更新
  3. 恢复：仅 UI 更新为 "running"
- **复用价值**: 中 — 暂停时安全松键的标准模式

### `check_pause(self)` — main.py:1417
- **作用**: 阻塞型暂停门卫，所有输入操作前调用，暂停时死等
- **实现**: `while self.is_paused and self.is_running: time.sleep(0.1)`
- **复用价值**: 高 — 最简单高效的协作式暂停机制，0 线程同步开销

---

## 分组：热键监听

### `start_hotkey_listener(self)` — main.py:1423
- **作用**: 启动后台全局热键监听线程（F8 停止 / F9 暂停 / F3 测试找图）
- **实现**:
  1. 内嵌 `hotkey_thread()` → `on_press(k)` 分发 F8/F9/F3
  2. `keyboard.Listener(on_press=on_press).join()` 阻塞监听
  3. `threading.Thread(daemon=True).start()`
- **复用价值**: 中 — pynput 全局热键监听的标准模式

---

## 分组：逻辑保障

### `set_english_input(self)` — main.py:1443
- **作用**: 强制切换前台窗口到英文键盘并关闭中文输入法
- **实现**:
  1. `LoadKeyboardLayoutW("00000409", 1)` 加载美式键盘
  2. `PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, ...)` 发送切换消息
  3. `SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)` 关闭 IME
- **复用价值**: 高 — 游戏脚本防中文输入污染的通用方案

### `is_game_foreground(self)` — main.py:1460
- **作用**: 检查游戏窗口（按 HWND 或 PID 匹配）是否当前为前台窗口
- **实现**:
  1. `GetForegroundWindow()` 取当前前台 HWND
  2. 若 game_hwnd 匹配则直接返回 True
  3. 否则 `GetWindowThreadProcessId` 比对 PID
- **复用价值**: 高 — 任何需要验证目标进程是否前台激活的场景

### `ensure_game_focus(self, reason="")` — main.py:1476
- **作用**: 任何输入操作前的焦点守卫，失焦时自动尝试恢复，1 秒内节流
- **实现**:
  1. `is_game_foreground()` 快速返回 True
  2. 距上次检查 < 1 秒则跳过（节流）
  3. 设置 `focus_recovering` 锁，调 `check_and_focus_game()`
- **复用价值**: 高 — 带节流 + 防重入的焦点守卫通用封装

### `check_and_focus_game(self)` — main.py:1505
- **作用**: 用 tasklist 查找 forzahorizon6.exe 进程，解析 PID，枚举其窗口并前台激活
- **实现**:
  1. `subprocess.check_output("tasklist /FI ...")` CSV 解析 PID
  2. `EnumWindows` 枚举窗口，匹配 PID，记录 hwnd 到列表
  3. (行 1520 截止，后续应有 `SetForegroundWindow` 调用)
- **复用价值**: 高 — 按进程名查找窗口并激活的通用 Windows 工具

---

## 汇总统计

| 类型 | 数量 |
|------|------|
| 模块级函数 | 1 (`check_windows_dependencies`) |
| ctypes 结构体类 | 5 (`KeyBdInput`, `HardwareInput`, `MouseInput`, `Input_I`, `Input`) |
| FH_UltimateBot 方法 | 47 |
| **合计函数/方法** | **48** |


---

# main.py 1520–2728 — 流程模块/导航/任务调度

# main.py 函数清单（行 1520–2728）

---

## 总览 (1520-2728)

本段覆盖 `FH_UltimateBot` 的三大原始业务模块（跑图 `logic_race`、买车 `logic_buy_car`、超级抽奖/专精 `logic_super_wheelspin`）及其支撑基础设施：游戏进程检测与聚焦、自动重启/开机状态机、菜单导航（`enter_menu`/`advanced_enter_menu`/`recover_to_menu`/`is_in_menu`）、任务管道调度（`start_pipeline`）、暂停恢复机制、输入法保障。此外还包含 AI/模板找车的调试辅助（`find_new_consumable_car_ai`、`save_strict_car_debug`、`cleanup_recent_strict_car_miss`）以及任务停止/热键监听。

**最具复用价值的导航子序列：**
- `enter_menu`：纯 ESC 轮询 + `collectionjournal.png` 锚点确认 → 进主菜单标准方式
- `advanced_enter_menu`：状态机退回，动态扫 `images/obstacles/` 弹窗点击 + ESC + VRAM 检测 → 故障恢复专用
- `logic_buy_car` 导航链：菜单 → PageDown → 收集簿 → 探索 → 车辆收集 → 品牌选择 → consumablecar
- `logic_super_wheelspin` 导航链：菜单 → PageDown → 购买新车与二手车 → 嘉年华内 PageDown → 设计涂装入口
- `restart_game_and_boot`：三阶段开机状态机（horizon6.png → continue-b/w → enter_menu）
- `start_pipeline`：三步任务调度器（race→buy→cj），含跳转表、全局循环计数、断点自动恢复

---

## 分组：找车 AI 与调试辅助

### `find_new_consumable_car_ai(self, region=None, save_miss=True)` — main.py:1058
- **作用**: 用 YOLO 模型在指定区域检测并返回"新消耗品车辆"的绝对坐标，miss 时可自动保存调试截图
- **实现**:
  1. `get_yolo_car_select_model()` 获取模型，无模型立即返回 None
  2. 截图 → `model.predict()` 获取检测框列表
  3. `find_yolo_car_candidate()` 按黄色标签比例评分选最佳候选
  4. miss 时调 `save_ai_car_debug`；pass 时返回绝对坐标 `(x, y)`
- **复用价值**: 高 — 任何需要 AI 找特定车辆的场景直接调用

### `save_strict_car_debug(self, screen_bgr, status, reason="", boxes=None, scores=None, click=None, force=False)` — main.py:1110
- **作用**: 将模板匹配找车结果（pass/miss）的原始截图和标注图写入 `debug/car_select/` 目录
- **实现**:
  1. miss 状态节流（1.5 秒内不重复保存）
  2. 写原始图到 `raw/`，绘制 bbox 和点击标记后写标注图到 `pass/` 或 `miss/`
  3. pass 时顺带调 `cleanup_recent_strict_car_miss` 清理近期 miss 图
- **复用价值**: 低 — 纯调试工具，业务复用价值有限

### `cleanup_recent_strict_car_miss(self, root, keep_seconds=12.0)` — main.py:1187
- **作用**: 在一次成功找车 (pass) 后，删除 `debug/car_select/miss/` 下 keep_seconds 内的 miss 截图（及对应 raw 图），减少磁盘噪音
- **实现**: 遍历 miss 目录，对 `mtime` 在 keep_seconds 内的文件执行 `os.remove`
- **复用价值**: 低 — 纯调试清理，可原样用于其他调试目录

---

## 分组：任务管道调度

### `start_pipeline(self, start_step)` — main.py:1211
- **作用**: 主任务启动入口，根据 start_step 决定从哪个模块开始，在 daemon 线程中循环执行 race→buy→cj 并管理跳转和恢复
- **实现**:
  1. 防重入检查；race 首次弹窗提示
  2. 初始化所有计数器、`is_running=True`，启动 UI 计时
  3. `runner()` 线程：`check_and_focus_game()` → while 循环按 `steps[curr_idx]` 分发到 `logic_race/logic_buy_car/logic_super_wheelspin`
  4. 失败时 `attempt_recovery()` 重试，连续失败超过 `MAX_RECOVERIES=10` 次则强制终止
  5. 成功后读取 UI 跳转表（`var_chk1/2/3` + `entry_next1/2/3`）计算 `next_idx`；`next_idx <= curr_idx` 时全局循环数 +1，超过 `total_loops` 时退出
- **复用价值**: 高 — 新增业务模块（如送车）需要独立 pipeline 时，此函数是最佳参考模板

### `stop_all(self)` — main.py:1347
- **作用**: 安全停止所有任务，释放所有按键、解除暂停锁、更新 UI 为 idle
- **实现**:
  1. `is_running = False`，`is_paused = False`
  2. 循环释放所有 DIK_CODES 按键 + 常用功能键
  3. `pydirectinput.mouseUp()`
  4. `finalize_active_task_time()` → `update_running_state("idle")`
- **复用价值**: 高 — 每个 pipeline 的结束都应调用此函数，或以此为模板

### `start_test_boot(self)` — main.py:1368
- **作用**: 独立测试自动开机识别流程（不跑业务），跑完后自动 `stop_all`
- **实现**: 设置 running 状态 → daemon 线程调 `restart_game_and_boot(force_test=True)` → 结果日志 → `stop_all`
- **复用价值**: 中 — 新功能调试时可照此写独立测试入口

---

## 分组：暂停与热键

### `toggle_pause(self)` — main.py:1396
- **作用**: 切换暂停/恢复状态，暂停时强制松开所有按键和鼠标
- **实现**: 翻转 `is_paused`；暂停时 `set_drive_keys_up()` + 所有功能键 `hw_key_up` + `mouseUp` + UI 更新为 "paused"；恢复时 UI 更新为 "running"
- **复用价值**: 高 — 新 pipeline 只要在循环中调用 `check_pause()` 即可无缝接入此暂停机制

### `check_pause(self)` — main.py:1417
- **作用**: 核心阻塞器，在任何动作前调用；暂停状态下无限 sleep 等待，直到恢复或停止
- **实现**: `while self.is_paused and self.is_running: time.sleep(0.1)`
- **复用价值**: 高 — 新模块的每个关键循环节点插入此调用即可支持 F9 暂停

### `start_hotkey_listener(self)` — main.py:1423
- **作用**: 后台监听键盘全局热键：F8=停止、F9=暂停、F3=测试找图
- **实现**: daemon 线程 + `pynput.keyboard.Listener`，`on_press` 按键分发到 `stop_all`/`toggle_pause`/`start_test_find_image`
- **复用价值**: 中 — 扩展新热键在此 `on_press` 中添加分支

---

## 分组：逻辑保障（输入法与焦点）

### `set_english_input(self)` — main.py:1443
- **作用**: 强制将游戏窗口切换到美式键盘并关闭中文输入法状态，防止中文输入污染游戏操作
- **实现**: Win32 `LoadKeyboardLayoutW("00000409")` → `PostMessageW(WM_INPUTLANGCHANGEREQUEST)` → `SendMessageW(WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)`
- **复用价值**: 高 — 每次聚焦游戏后应调用，已在 `check_and_focus_game` 中集成

### `is_game_foreground(self)` — main.py:1460
- **作用**: 快速检查游戏窗口是否是当前前台窗口（先比 hwnd，再比 PID）
- **实现**: `GetForegroundWindow()` → 与 `self.game_hwnd` 直接比较 → 否则通过 `GetWindowThreadProcessId` 比对 PID
- **复用价值**: 中 — 任何需要"先确认焦点再操作"的场景可直接用

### `ensure_game_focus(self, reason="")` — main.py:1476
- **作用**: 操作前确保游戏窗口有焦点；失焦时最多每1秒尝试一次恢复（防抖），防止重入
- **实现**: 调 `is_game_foreground()` → 若失焦且距上次检查 >1 秒 → 设 `focus_recovering=True` 防重入 → 调 `check_and_focus_game()` → finally 重置 flag
- **复用价值**: 中 — 可在任何 hw_press/game_click 前加保护调用

### `check_and_focus_game(self)` — main.py:1505
- **作用**: 通过 `tasklist` 确认 `forzahorizon6.exe` 进程存在，并将其窗口提到前台；同时更新识图区域和显示器边界
- **实现**:
  1. `tasklist /FI` 解析 PID
  2. `EnumWindows` 找属于该 PID 的可见窗口
  3. `ShowWindow(SW_RESTORE/SW_SHOW)` + `SetForegroundWindow`
  4. 拦截过小窗口（<1000×600）判定为启动闪屏
  5. `update_regions_by_window` + `GetMonitorInfoW` 更新识图区域和屏幕边界
  6. `set_english_input()`
- **复用价值**: 高 — 任何模块开始前的标准前置步骤

---

## 分组：游戏启动与开机状态机

### `restart_game_and_boot(self, force_test=False)` — main.py:1611
- **作用**: 执行完整自动开机流程：发 Steam 启动命令 → 等进程 → 三阶段状态机识图 → 进菜单
- **实现**:
  1. 检查 `var_auto_restart` 开关（非 force_test 时）
  2. `os.system(restart_cmd)` 启动游戏
  3. 最多等 120 秒检测进程（`check_and_focus_game`）
  4. 5 分钟状态机循环：
     - **画面1**：透明+轮廓双策略识别 `horizon6.png` → 按两次 Enter → 等 10 秒
     - **画面2**：识别 `continue-b/w.png` → 点击 → 刷新时间戳
     - **状态转化**：30 秒未见画面2 → `enter_menu()` 验证进入漫游
- **复用价值**: 高 — 完整的开机恢复链，新 pipeline 在 `attempt_recovery` 中已集成调用

### `handle_vramne_restart(self)` — main.py:1736
- **作用**: 检测到 VRAMNE 显存不足时停止脚本（已禁用强杀）并交由人工处理
- **实现**: 打日志 → 返回 False
- **复用价值**: 低 — 仅作异常处置钩子

### `check_vramne_during_race(self)` — main.py:1741
- **作用**: 跑图循环中每隔 3 秒快速检测 `VRAMNE.png`，发现则触发 `handle_vramne_restart`
- **实现**: `find_image_gray("VRAMNE.png", fast_mode=True)` → 命中调 `handle_vramne_restart()`
- **复用价值**: 中 — 任何长时间循环中可插入此检测保障

### `attempt_recovery(self)` — main.py:1755
- **作用**: 统一断点恢复入口：进程不在则重启，进程在则用 `advanced_enter_menu` 退回菜单
- **实现**: `check_and_focus_game()` → 失败走 `restart_game_and_boot()` → 成功走 `advanced_enter_menu()`
- **复用价值**: 高 — `start_pipeline` 失败恢复直接调用，新 pipeline 也应在失败时调用

### `wait_for_freeroam(self)` — main.py:1769
- **作用**: 验证游戏是否处于漫游界面（识别 `anna.png`），否则循环按 ESC 等待
- **实现**: 最多 100 次循环，每次识别 `anna.png`（左下角），未找到则 `hw_press("esc")` + 等 2 秒
- **复用价值**: 中 — 开机后或异常后确认已回漫游时使用

---

## 分组：菜单导航（核心复用区）

### `recover_to_menu(self)` — main.py:1790
- **作用**: 薄封装，直接调 `enter_menu()`，作为语义更清晰的"退回菜单"接口
- **实现**: `return self.enter_menu()`
- **复用价值**: 中 — 业务代码通过此名称调用更具可读性

### `is_in_menu(self)` — main.py:1794
- **作用**: 单次快速判断当前是否在主菜单（识别 `collectionjournal.png`，反色模式）
- **实现**: `find_image_gray("collectionjournal.png", invert_mode=True, threshold=0.66)` 一次调用，返回位置或 None
- **复用价值**: 高 — `advanced_enter_menu` 和导航前置检查的终止条件

### `enter_menu(self)` — main.py:1802
- **作用**: 标准进菜单：循环按 ESC + 轮询 `collectionjournal.png`，最多 60 次
- **实现**:
  1. 最多 60 次循环
  2. 每次调 `find_image_gray("collectionjournal.png", invert_mode=True)`
  3. 找到立即返回 True；未找到 → `hw_press("esc")` → `sleep(1.0)`
  4. 60 次耗尽返回 False
- **复用价值**: 高 — 所有业务模块（race/buy/cj）开始前的标准前置调用

### `advanced_enter_menu(self)` — main.py:1830
- **作用**: 高级状态机退回菜单，专门用于故障恢复；能识别并点击中途弹窗，而非盲目按 ESC
- **实现**:
  1. 动态扫描 `images/obstacles/` 下所有 png/jpg 构建障碍物列表
  2. 最多 80 次循环：
     - `is_in_menu()` → 成功返回
     - `find_image_gray("VRAMNE.png")` → 放弃返回 False
     - `find_any_image_gray(dynamic_obstacles)` → 找到则点击（跳过 ESC）
     - 以上都没有 → `hw_press("esc")`
- **复用价值**: 高 — 新 pipeline 的 `attempt_recovery` 分支中复用；obstacles 文件夹可扩展新弹窗图片

---

## 分组：跑图模块

### `logic_race(self, target_count)` — main.py:1889
- **作用**: 完整跑图循环：进菜单 → 创意中心 → EventLab → 输入蓝图代码 → 选刷图车 → 循环开跑并计数
- **实现**:
  1. 满足 `race_counter >= target_count` 立即返回 True
  2. `enter_menu()` → 连按 4 次 PageDown 到创意中心 → 等待 `eventlab.png` → 点击
  3. 等待 `playenent.png`（游玩赛事）→ 点击 → Backspace → Up → Enter 进搜索框
  4. 等待 `sharecode-dialog.png` → 逐字符输入 share code → Enter → Down → Enter
  5. 轮询 20 秒等待蓝图结果（`VEI.png`），若出现 `racenotfound.png` 则调 `abort_invalid_blueprint_and_back_to_roam`
  6. Enter×2 进赛事 → `find_skill_car_with_like_tag` 找刷图车；未找到则选品牌(`skillcarbrand.png`) + 翻页
  7. 选车 → Enter → 等 `start.png/startw.png`
  8. 主循环：`set_drive_keys_down` → 每 3 秒检 VRAM+作者评价，每 1 秒检 `restart.png`；超时按 ESC + `restarta.png` 重开
  9. 完赛：最后一圈 Enter，否则 X+Enter；`race_counter += 1`
- **复用价值**: 高 — 蓝图输入序列、刷图车选车逻辑、超时重开机制均可独立复用

### `abort_invalid_blueprint_and_back_to_roam(self)` — main.py:2229
- **作用**: 蓝图失效时设置 `invalid_blueprint_abort=True` 标志并按 3 次 ESC 退出，返回 False 触发上层停止
- **实现**: `self.invalid_blueprint_abort = True` → 3×`hw_press("esc")` → return False
- **复用价值**: 中 — 任何蓝图/赛事失效场景可复用此异常出口

### `handle_author_prompt(self, release_drive_keys=False)` — main.py:2239
- **作用**: 检测并跳过赛后作者评价弹窗（likeauthor/dislikeauthor）
- **实现**: `find_any_image_gray(["likeauthor.png","dislikeauthor.png"], invert_mode=True)` → 若有则可选松开油门 → 连按 2 次 Enter + sleep 0.8 → 返回 True
- **复用价值**: 高 — 任何赛事结算流程后必须调用；跑图中每 3 秒调一次

---

## 分组：买车模块

### `logic_buy_car(self, target_count)` — main.py:2265
- **作用**: 批量购买消耗品车辆：进菜单 → 收集簿 → 探索 → 车辆收集 → 选品牌 → 选车 → 循环购买
- **实现**:
  1. `enter_menu()` → 等待并双击 `collectionjournal.png`（收集簿）
  2. 双击 `masterexplorer.png`（探索） → 双击 `carcollection.png`（车辆收集）
  3. Backspace → 轮询 `CCbrand.png`（消耗品品牌，最多 5 次按 Up 尝试）→ 点击品牌 → Down
  4. 等待 `consumablecar.png`（threshold=0.90）→ 双击进入购买页
  5. while 循环：Space → Down → Enter×3（选车+确认+确认）→ `car_counter += 1`
  6. 购完后 5×ESC 退出
- **复用价值**: 高 — 进收集簿/车辆收集的导航序列可直接复用于需要访问车库的场景

---

## 分组：抽奖/专精模块（超级 Wheelspin = 消耗技能点）

### `enter_design_paint_choose_car(self)` — main.py:2400
- **作用**: 在"车辆菜单"中找到"设计与涂装"按钮并点击，再找到"选车"按钮并点击，进入车辆列表
- **实现**:
  1. `wait_for_any_image_gray(["designpaint-w.png","designpaint-b.png"])` → 点击
  2. 等待 `choosecar.png/choosecar-b.png`；未找到则 Enter 再等一次
  3. 点击 choosecar → sleep 1.5 → 返回 True
- **复用价值**: 高 — 进入车辆列表的标准入口，送车模块等需要换车的流程可直接调用

### `select_new_consumable_car_from_list(self)` — main.py:2444
- **作用**: 在车辆列表中按品牌过滤，翻页查找并选中"新消耗品车辆"（支持智能记忆页码跳页）
- **实现**:
  1. Backspace 触发筛选 → 轮询 `CCbrand.png`（最多 30 次 Up 回滚）→ 点击品牌
  2. 若 `smart_page` 开启，跳过前 `memory_car_page-1` 页（4×Right × N）
  3. 最多翻 85 页：每页调 `wait_for_new_consumable_car_strict` → 找到则点击并记录页码；未找到则 4×Right 翻页
  4. 找到更新 `memory_car_page`；未找到重置页码
- **复用价值**: 高 — 送车模块也需要从列表选消耗品车，此函数直接复用

### `logic_super_wheelspin(self, target_count)` — main.py:2520
- **作用**: 超级抽奖主流程（实为消耗技能点专精）：进菜单 → 车辆菜单 → 选消耗品车 → 进专精 → 消耗技能点 → 计数
- **实现**:
  1. `enter_menu()` → PageDown → `wait_for_buy_and_used_car` → 点击 → Enter → 等 `buyandsell-w/b.png`
  2. 嘉年华内 PageDown → while 循环：`enter_design_paint_choose_car` → `select_new_consumable_car_from_list`
  3. 识别 `rc.png`（上车按钮）或 Enter×2 上车 → 等待 `spraycar-w.png` 确认进入喷漆页
  4. ESC 退回 → 等 `designpaint-w/b.png` 稳定 → Up → Enter 进升级调校
  5. 等 `clsldcnw/b.png`（车辆专精）→ 点击 → 等 `EXPwU.png`（已点过则跳过）
  6. Enter → 按 `config["skill_dirs"]` 方向键 + Enter 点技能；检测 `SPNE.png`（技能点不足）→ 触发 `should_switch_skillcar_after_cj`
  7. `cj_counter += 1` → `return_to_vehicle_menu_after_mastery` 回到车辆菜单
  8. 全部完成后视 `should_switch_skillcar_after_cj` 决定是否切换刷图车
- **复用价值**: 高 — 进嘉年华购车区的导航序列（菜单→PageDown→buy_and_used_car）是进车辆商城的通用路径


---

# ui_layout.py + app_resources.py — GUI 构建/资源

# FH6 Bot UI Inventory

## 总览

`ui_layout.py` 内定义唯一入口 `setup_ui(bot)`，在函数体内声明 `colors` 调色板及四个局部工厂函数（`card`/`label`/`entry`/`button`），再用 `create_task_card` 批量搭建三个任务卡片，最后构建运行时状态栏、守护设置栏和日志区域。所有运行时控件均挂载到 `bot.*` 属性，外部代码通过 `bot.btn_xxx`、`bot.entry_xxx`、`bot.lbl_xxx` 访问。`app_resources.py` 负责路径解析，配置文件路径为 `USER_CONFIG_FILE = <APP_DIR>/config.json`，版本号常量 `CURRENT_VERSION = "3.2"`。

**新增 GUI 按钮/控件所需清单：**
- 颜色：从 `bot.ui_colors`（即 `colors` dict）取值，可用键见下文。
- 按钮：在 `setup_ui` 作用域内调用 `button(parent, text, command, *, color, hover, width, height, text_color)`。
- 若在运行时控件栏添加，父容器为 `bot.runtime_frame`（`card`，高 66px）；用 `.pack(side="right", ...)` 排列。
- 若在任务卡片中添加，调用 `create_task_card` 返回 `(box, btn, count_entry, progress)`，之后向 `box` 继续 `.grid()` 新行。
- 配置新 key：在 `bot.config` 读取时用 `.get("new_key", default)`，持久化写入 `USER_CONFIG_FILE`（`<APP_DIR>/config.json`）。

---

## ui_layout.py — 调色板 `colors`

| 键 | 值 | 说明 |
|---|---|---|
| `bg` | `#0B0B0C` | 全局背景 |
| `panel` | `#151516` | 卡片背景 |
| `panel_2` | `#1C1C1E` | Entry 背景 |
| `panel_3` | `#232326` | 技能格 / 状态标签背景 |
| `line` | `#2F2F33` | 边框线 |
| `text` | `#F5F5F7` | 主文字 |
| `muted` | `#A1A1AA` | 次要文字 |
| `muted_2` | `#71717A` | 更次要文字 |
| `blue` | `#0A84FF` | 跑图任务主色 |
| `blue_hover` | `#006EDB` | 跑图 hover |
| `green` | `#30D158` | 买车任务主色 |
| `green_hover` | `#27B84D` | 买车 hover |
| `purple` | `#BF5AF2` | 超抽任务主色 / AI 开关色 |
| `purple_hover` | `#A84DDD` | 超抽 hover |
| `yellow` | `#FFD60A` | 暂停按钮 |
| `red` | `#FF453A` | 停止 / 清除按钮 |
| `red_hover` | `#D9362E` | 红色 hover |
| `button` | `#2C2C2E` | 默认按钮背景 |
| `button_hover` | `#3A3A3C` | 默认按钮 hover |

> 调色板存入 `bot.ui_colors`，setup_ui 外可通过 `bot.ui_colors["blue"]` 访问。

---

## ui_layout.py — 工厂/辅助函数

### `card(parent, **kwargs)` — ui_layout.py:37
- **作用**: 创建统一样式的圆角面板 Frame（panel 底色 + line 边框）
- **实现**: 构造默认 opts dict 后 `opts.update(kwargs)`，返回 `CTkFrame`
- **复用价值**: 高

### `label(parent, text, *, color=None, font=None, **kwargs)` — ui_layout.py:47
- **作用**: 创建标准文字标签，默认颜色 `text`，默认字体 `font_body`（13px）
- **实现**: 薄封装 `CTkLabel`，color/font 可覆盖
- **复用价值**: 高

### `entry(parent, width=76, height=32, **kwargs)` — ui_layout.py:56
- **作用**: 创建统一样式的输入框（panel_2 底色 + line 边框 + 居中对齐）
- **实现**: 薄封装 `CTkEntry`，`justify` 默认 center 可被 kwargs 覆盖
- **复用价值**: 高

### `button(parent, text, command, *, color=None, hover=None, width=96, height=34, text_color="#FFFFFF")` — ui_layout.py:72
- **作用**: 创建统一样式按钮（圆角 8、粗体 13px），color/hover 默认为 button/button_hover
- **实现**: 薄封装 `CTkButton`，所有视觉参数内置
- **复用价值**: 高（是添加新按钮的标准入口）

### `create_task_card(parent, col, title, subtitle, btn_text, btn_cmd, btn_color, btn_hover, count_value)` — ui_layout.py:107
- **作用**: 在 `bot.config_frame` 的指定列创建一张完整任务卡片（标题、副标题、启动按钮、次数输入框、进度标签）
- **实现**: 调用 `card`/`label`/`button`/`entry`，grid 布局，返回 `(box, btn, count_entry, progress)`
- **复用价值**: 高（新增第四个任务类型时直接复用）

### `make_runtime_label(title, value="--")` — ui_layout.py:314
- **作用**: 在 `bot.runtime_frame` 中创建一个"标题+值"双行运行时信息标签
- **实现**: 内嵌 `CTkFrame`，两个 `label`，`pack(side="left")`，返回值标签
- **复用价值**: 中（仅在 runtime_frame 内使用）

---

## ui_layout.py — `setup_ui(bot)` 结构总览

```
setup_ui(bot)
├── 全局样式设置（Dark mode, fg_color）
├── colors dict 定义 → bot.ui_colors
├── 字体定义（font_title/section/body/small）
├── 局部工厂：card / label / entry / button
├── BooleanVar 定义（var_chk1/2/3, var_ai_assist, var_smart_page, var_ai_only, var_ai_auto_capture, var_auto_restart）
│
├── bot.main_container（CTkFrame, transparent, padx/pady=18）
│   ├── bot.config_frame（4列 grid）
│   │   ├── 列0: 任务卡片"循环跑图" → box_race, bot.btn_race, bot.entry_race, bot.lbl_race
│   │   │       + bot.entry_share（蓝图代码输入框）
│   │   ├── 列1: 任务卡片"批量买车" → box_car, bot.btn_car, bot.entry_car, bot.lbl_car
│   │   ├── 列2: 任务卡片"超级抽奖" → box_cj, bot.btn_cj, bot.entry_cj, bot.lbl_cj
│   │   │       + assist_row（AI辅助/智能页码/纯AI/自动截图 四个 CTkSwitch）
│   │   │       + skill_area（4×4 技能格 grid_labels + 方向按钮 + 清除按钮）
│   │   └── 列3: bot.side_panel（流程设置）
│   │           + next_grid（3行 CheckBox + Entry：跑图➡买车/买车➡抽奖/抽奖➡跑图）
│   │             → bot.entry_next1/2/3, bot.chk1/2/3
│   │
│   ├── bot.global_settings_frame（高52，守护设置栏）
│   │   ├── label "守护设置"
│   │   ├── bot.entry_global_loop（大循环次数）
│   │   ├── bot.entry_race_timeout（单局超时）
│   │   ├── bot.entry_drive_keys（加速键）
│   │   └── bot.btn_test_boot（"测试启动"按钮）
│   │
│   ├── bot.runtime_frame（高66，运行时状态栏）
│   │   ├── bot.lbl_run_state（待机/运行状态标签）
│   │   ├── bot.lbl_runtime_task（当前任务）
│   │   ├── bot.lbl_runtime_progress（任务进度）
│   │   ├── bot.lbl_runtime_loop（大循环）
│   │   ├── bot.lbl_runtime_task_time（本任务耗时）
│   │   ├── bot.lbl_runtime_total_time（总运行时间）
│   │   ├── bot.lbl_runtime_totals（模块累计）
│   │   ├── bot.btn_runtime_gift（"自动送车"，purple）pack side=right
│   │   ├── bot.btn_runtime_gift_test（"送车测试"，#5A6473）pack side=right
│   │   ├── bot.btn_runtime_pause（"暂停 F9"，yellow，初始disabled）pack side=right
│   │   └── bot.btn_runtime_stop（"停止 F8"，red，初始disabled）pack side=right
│   │
│   ├── bot.log_header（日志标题行）
│   │   ├── bot.lbl_log_title（"运行日志"）
│   │   └── bot.btn_toggle_log（"收起日志"）
│   │
│   └── bot.bottom_frame（日志区域）
│       ├── bot.btn_stop（"等待指令 (F8)"，150×58，side=left）
│       └── bot.log_box（CTkTextbox，只读，wrap=word）
│
└── FocusOut 绑定（entry_next1/2/3 → normalize_step_entry）
```

---

## app_resources.py — 路径常量与工具函数

### `get_app_dir()` — app_resources.py:7
- **作用**: 返回程序根目录（打包后为 exe 所在目录，开发时为脚本所在目录）
- **实现**: 检测 `sys.frozen`，打包用 `sys.executable`，开发用 `__file__`
- **复用价值**: 高

### `get_internal_dir()` — app_resources.py:13
- **作用**: 返回内置资源目录（打包后为 PyInstaller _MEIPASS，开发时同 get_app_dir）
- **实现**: 检测 `sys._MEIPASS` 属性
- **复用价值**: 高

### `auto_extract_configs()` — app_resources.py:29
- **作用**: 向下兼容旧版配置文件名，自动将 bot_config.json / bot-config.json 等迁移/重命名为 config.json
- **实现**: 遍历老路径列表，`shutil.move` 到 USER_CONFIG_FILE；确保 CONFIG_DIR 存在
- **复用价值**: 低（仅启动时调用一次）

### `auto_extract_images(folder_name="images")` — app_resources.py:49
- **作用**: 将打包内置的 images 目录释放到程序外部目录（不覆盖用户已有文件）
- **实现**: `os.walk` 内置 images，仅当外部文件不存在时 `shutil.copy2`
- **复用价值**: 低

### `get_img_path(filename)` — app_resources.py:77
- **作用**: 解析图片文件路径，优先外部 images/（允许用户替换），回退内置 images/，带内存缓存
- **实现**: LRU-like dict 缓存挂在函数对象上，依次检查 APP_DIR/images 和 INTERNAL_DIR/images
- **复用价值**: 高（所有图片加载均应通过此函数）

### `get_asset_path(*parts)` — app_resources.py:108
- **作用**: 解析 assets 目录内置资源路径（仅内置，不允许用户替换）
- **实现**: 先查 INTERNAL_DIR/assets，再查 APP_DIR/assets，不存在返回 None
- **复用价值**: 中

---

## 路径常量速查

| 常量 | 路径 | 说明 |
|---|---|---|
| `APP_DIR` | `get_app_dir()` | 程序根目录 |
| `INTERNAL_DIR` | `get_internal_dir()` | 内置资源目录 |
| `CONFIG_DIR` | `APP_DIR/config` | 配置子目录 |
| `USER_CONFIG_FILE` | `APP_DIR/config.json` | **主配置文件** |
| `LOG_FILE` | `APP_DIR/bot_log.txt` | 运行日志 |
| `CACHE_DIR` | `APP_DIR/cache` | 缓存目录 |
| `TEMPLATE_CACHE_FILE` | `CACHE_DIR/template_cache.pkl` | 模板缓存 |
| `TEMPLATE_META_FILE` | `CACHE_DIR/template_meta.json` | 模板元数据 |
| `CURRENT_VERSION` | `"3.2"` | 当前版本号 |
