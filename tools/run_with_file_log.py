import ctypes
import os
import sys
import time
import traceback

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pyautogui
import win32gui
from PIL import ImageGrab

from app_resources import get_app_dir
from main import FH_UltimateBot


def get_window_title(hwnd):
    try:
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def find_forza_client_rect():
    found = []

    def enum_window(hwnd, _):
        try:
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            title = get_window_title(hwnd)
            if "Forza Horizon" not in title:
                return True
            rect = win32gui.GetClientRect(hwnd)
            x, y = win32gui.ClientToScreen(hwnd, (0, 0))
            found.append((hwnd, title, x, y, rect[2], rect[3]))
        except Exception:
            pass
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(enum_proc(enum_window), 0)
    return found[0] if found else None


class LoggedBot(FH_UltimateBot):
    def __init__(self, log_path):
        self._file_log_path = log_path
        super().__init__()
        self.log(f"[ParsecTest] file log: {log_path}")

    def log(self, message):
        curr_time = time.strftime("%H:%M:%S")
        try:
            os.makedirs(os.path.dirname(self._file_log_path), exist_ok=True)
            with open(self._file_log_path, "a", encoding="utf-8") as f:
                f.write(f"[{curr_time}] {message}\n")
        except Exception:
            pass
        return super().log(message)


def install_heartbeat(app):
    def heartbeat():
        try:
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            fg_title = get_window_title(fg_hwnd)
            screen_size = pyautogui.size()
            capture_status = "not-tested"
            forza = find_forza_client_rect()

            try:
                if forza:
                    _, _, x, y, w, h = forza
                    img = ImageGrab.grab(
                        bbox=(x, y, x + min(w, 24), y + min(h, 24)),
                        all_screens=True,
                    )
                else:
                    img = ImageGrab.grab(bbox=(0, 0, 24, 24), all_screens=True)
                capture_status = f"ok size={img.size}"
            except Exception as exc:
                capture_status = f"fail {type(exc).__name__}: {exc}"

            if forza:
                _, title, x, y, w, h = forza
                forza_text = f"forza='{title}' client=({x},{y},{w},{h})"
            else:
                forza_text = "forza=not-found"

            app.log(
                "[ParsecTest] heartbeat "
                f"is_running={getattr(app, 'is_running', None)} "
                f"foreground='{fg_title}' screen={screen_size.width}x{screen_size.height} "
                f"capture={capture_status} {forza_text}"
            )
        except Exception as exc:
            app.log(f"[ParsecTest] heartbeat exception: {exc}")
        finally:
            app.after(10000, heartbeat)

    app.after(1000, heartbeat)


if __name__ == "__main__":
    log_dir = os.path.join(get_app_dir(), "debug")
    log_path = os.path.join(log_dir, f"parsec_disconnect_test_{time.strftime('%Y%m%d_%H%M%S')}.log")
    try:
        app = LoggedBot(log_path)
        install_heartbeat(app)
        app.mainloop()
    except Exception:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
