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
