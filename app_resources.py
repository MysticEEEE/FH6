import os
import sys
import shutil


# ==========================================
def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_internal_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return get_app_dir()


APP_DIR = get_app_dir()
INTERNAL_DIR = get_internal_dir()
# 【新增 config 目录路径】
CONFIG_DIR = os.path.join(APP_DIR, "config")
USER_CONFIG_FILE = os.path.join(APP_DIR, "config.json")      # <--- 全面替换为 config.json
LOG_FILE = os.path.join(APP_DIR, "bot_log.txt")
CACHE_DIR = os.path.join(APP_DIR, "cache")
TEMPLATE_CACHE_FILE = os.path.join(CACHE_DIR, "template_cache.pkl")
TEMPLATE_META_FILE = os.path.join(CACHE_DIR, "template_meta.json")
CURRENT_VERSION = "2.2"
def auto_extract_configs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # 向下兼容，自动重命名并迁移老版本 bot_config
    old_configs = [
        os.path.join(APP_DIR, "bot_config.json"),
        os.path.join(APP_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot_config.json"),
        os.path.join(CONFIG_DIR, "config.json")
    ]
    for old_path in old_configs:
        if os.path.exists(old_path):
            try:
                if not os.path.exists(USER_CONFIG_FILE):
                    shutil.move(old_path, USER_CONFIG_FILE)
                else:
                    os.remove(old_path)
            except Exception:
                pass
def auto_extract_images(folder_name="images"):
    internal_dir = os.path.join(INTERNAL_DIR, folder_name)
    external_dir = os.path.join(APP_DIR, folder_name)

    if not os.path.isdir(internal_dir):
        print(f"[auto_extract_images] 内置目录不存在: {internal_dir}")
        return

    try:
        os.makedirs(external_dir, exist_ok=True)

        for root, dirs, files in os.walk(internal_dir):
            rel_path = os.path.relpath(root, internal_dir)
            target_root = external_dir if rel_path == "." else os.path.join(external_dir, rel_path)
            os.makedirs(target_root, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_root, file)

                # 只在外部不存在时释放，保留用户自定义替换
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)

    except Exception as e:
        print(f"[auto_extract_images] 释放 images 失败: {e}")


def get_img_path(filename):
    rel_name = os.path.normpath(str(filename))
    basename = os.path.basename(rel_name)
    cache = getattr(get_img_path, "_cache", None)
    if cache is None:
        cache = {}
        setattr(get_img_path, "_cache", cache)
    if rel_name in cache:
        return cache[rel_name]

    if os.path.isabs(rel_name) and os.path.exists(rel_name):
        cache[rel_name] = rel_name
        return rel_name

    # 优先读取程序目录外部 images（允许用户替换），保留 obstacles/xxx.png 等子目录结构。
    for candidate_name in (rel_name, basename):
        ext_path = os.path.join(APP_DIR, "images", candidate_name)
        if os.path.exists(ext_path):
            cache[rel_name] = ext_path
            return ext_path

        # 外部没有则读取内置 images
        int_path = os.path.join(INTERNAL_DIR, "images", candidate_name)
        if os.path.exists(int_path):
            cache[rel_name] = int_path
            return int_path

    cache[rel_name] = filename
    return filename


def get_asset_path(*parts):
    """
    assets 只允许读取内置资源：
    - 打包后：_MEIPASS/assets
    - 开发环境：项目目录/assets
    """
    asset_path = os.path.join(INTERNAL_DIR, "assets", *parts)
    if os.path.exists(asset_path):
        return asset_path

    dev_asset_path = os.path.join(get_app_dir(), "assets", *parts)
    if os.path.exists(dev_asset_path):
        return dev_asset_path

    return None

