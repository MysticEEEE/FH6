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
    """送车功能写入 config 的默认项。gift_max_count=0 表示送到没有为止（不限数量）。"""
    return {"gift_max_count": 0, "chk_gift": False}
