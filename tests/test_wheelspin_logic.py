import unittest
from wheelspin_logic import should_stop_wheelspin, wheelspin_default_config


class TestShouldStopWheelspin(unittest.TestCase):
    def _ok(self, **kw):
        base = dict(returned_to_menu=False, spin_count=0, max_count=0)
        base.update(kw)
        return should_stop_wheelspin(**base)

    def test_continue_normal(self):
        stop, reason = self._ok()
        self.assertFalse(stop)
        self.assertEqual(reason, "")

    def test_stop_on_returned_to_menu(self):
        stop, reason = self._ok(returned_to_menu=True)
        self.assertTrue(stop)
        self.assertIn("菜单", reason)

    def test_stop_on_max_count(self):
        stop, reason = self._ok(spin_count=50, max_count=50)
        self.assertTrue(stop)
        self.assertIn("上限", reason)

    def test_max_count_zero_means_unlimited(self):
        stop, reason = self._ok(spin_count=99999, max_count=0)
        self.assertFalse(stop)

    def test_returned_to_menu_takes_priority(self):
        stop, reason = self._ok(returned_to_menu=True, spin_count=1, max_count=50)
        self.assertTrue(stop)
        self.assertIn("菜单", reason)


class TestDefaultConfig(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(
            wheelspin_default_config(),
            {"wheelspin_mode": "抽奖", "wheelspin_max_count": 0, "wheelspin_owned_downs": 2},
        )


if __name__ == "__main__":
    unittest.main()
