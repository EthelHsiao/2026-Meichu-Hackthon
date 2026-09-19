import unittest

from collectors import LinuxDesktopCollector


class FixtureRunner:
    def __init__(self, values):
        self.values = values

    def __call__(self, args):
        return self.values[tuple(args)]


class FailingRunner:
    def __call__(self, args):
        raise OSError("utility unavailable")


class CollectorTests(unittest.TestCase):
    def test_collects_foreground_idle_and_processes_from_fixture_commands(self):
        runner = FixtureRunner(
            {
                ("xdotool", "getactivewindow"): "42\n",
                ("xdotool", "getwindowname", "42"): "Proposal.odt — LibreOffice\n",
                ("xprop", "-id", "42", "_NET_WM_PID"): "_NET_WM_PID(CARDINAL) = 123\n",
                ("ps", "-p", "123", "-o", "comm="): "libreoffice\n",
                ("ps", "-eo", "comm="): "libreoffice\nchrome\n",
                ("xprintidle",): "4000\n",
            }
        )
        state = LinuxDesktopCollector(runner=runner).collect()
        self.assertEqual(state["foreground"]["app"], "libreoffice")
        self.assertEqual(state["foreground"]["window_title"], "Proposal.odt")
        self.assertEqual(state["system"]["idle_seconds"], 4)
        self.assertEqual(state["system"]["running_apps"], ["chrome", "libreoffice"])

    def test_optional_enricher_failure_is_nullable(self):
        state = LinuxDesktopCollector(runner=FailingRunner()).collect()
        self.assertIsNone(state["enrichments"]["git"])
        self.assertIsNone(state["foreground"]["app"])


if __name__ == "__main__":
    unittest.main()
