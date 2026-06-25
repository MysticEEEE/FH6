"""自动抽奖流程的纯决策逻辑（无 GUI / OpenCV 依赖，便于单测）。

与 gift_logic.py 对应：把"是否停止"这类纯判断从带 UI/识图副作用的主流程里抽离，
方便单元测试，主流程只负责识图与按键。
"""


def should_stop_wheelspin(*, returned_to_menu, spin_count, max_count):
    """判断抽奖循环是否应停止。返回 (should_stop, reason)。

    优先级：退回「我的地平线」菜单（确定性结束信号） > 达到次数上限（安全阀）。
    max_count == 0 表示不限次数（抽完为止）。
    """
    if returned_to_menu:
        return True, "已退回「我的地平线」菜单，抽奖次数已用尽"
    if max_count and spin_count >= max_count:
        return True, f"达到最大抽奖次数上限 {max_count}"
    return False, ""


def wheelspin_default_config():
    """抽奖功能写入 config 的默认项。"""
    return {
        # 抽奖类型："抽奖" 或 "超级抽奖"
        "wheelspin_mode": "抽奖",
        # 最大抽奖次数上限（0=不限，抽完为止）
        "wheelspin_max_count": 0,
        # 「已拥有车辆」对话框中，从默认高亮项按几次「下」到「出售」项。
        # 截图17（普通抽奖）默认高亮在「添加至车库」(项1)，下×2 到「出售」(项3)。
        # 截图22/23（超级抽奖）疑似默认已高亮「出售」，实机需核对此值（见 README/报告）。
        "wheelspin_owned_downs": 2,
    }
