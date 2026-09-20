import unittest

import config
from sensing.gestures import GestureDetector

HIGH, LOW = config.FSR_PRESS_RAW + 1000, 100
REST_ACCEL, REST_GYRO = [0.0, 0.0, 9.81], [0.0, 0.0, 0.0]


def frame(t, fsr=(LOW, LOW), accel=REST_ACCEL, gyro=REST_GYRO):
    return {"type": "telemetry", "uptime_ms": t, "fsr": {"enabled": True, "raw": list(fsr)},
            "imu": {"ok": True, "accel_m_s2": accel, "gyro_rad_s": gyro}}


def run(frames):
    d = GestureDetector()
    return [(e.kind, e.dur_ms) for f in frames for e in d.feed(f)]


def kinds(frames):
    return [k for k, _ in run(frames)]


class GestureTests(unittest.TestCase):
    def test_resting_produces_nothing(self):
        self.assertEqual(kinds([frame(t) for t in range(0, 5000, 50)]), [])

    def test_squeeze_both_fsr_held(self):
        frames = [frame(t, (HIGH, HIGH) if 1000 <= t < 2000 else (LOW, LOW)) for t in range(0, 3000, 50)]
        self.assertEqual(kinds(frames), ["squeeze"])

    def test_single_quick_press_is_pat_after_confirm_window(self):
        frames = [frame(t, (LOW, HIGH) if 1000 <= t < 1150 else (LOW, LOW)) for t in range(0, 3000, 50)]
        events = run(frames)
        self.assertEqual([k for k, _ in events], ["pat"])

    def test_fsr1_double_press_is_left_to_firmware_double_tap(self):
        def fsr(t):
            return (HIGH, LOW) if 1000 <= t < 1100 or 1300 <= t < 1400 else (LOW, LOW)
        self.assertEqual(kinds([frame(t, fsr(t)) for t in range(0, 3000, 50)]), [])

    def test_long_single_press_is_not_pat(self):
        frames = [frame(t, (HIGH, LOW) if 1000 <= t < 1800 else (LOW, LOW)) for t in range(0, 3000, 50)]
        self.assertEqual(kinds(frames), [])

    def test_shake_once_with_cooldown(self):
        def accel(t):
            if 1000 <= t < 2000:
                return [0.0, 0.0, 9.81 + (12 if (t // 50) % 2 else -12)]
            return REST_ACCEL
        frames = [frame(t, accel=accel(t), gyro=[0, 0, 3] if 1000 <= t < 2000 else REST_GYRO) for t in range(0, 6000, 50)]
        self.assertEqual(kinds(frames).count("shake"), 1)

    def test_lift_then_putdown(self):
        def moving(t):
            return 3000 <= t < 5000
        frames = [frame(t, accel=[0.0, 1.5, 10.5] if moving(t) else REST_ACCEL,
                        gyro=[0.8, 0, 0] if moving(t) else REST_GYRO) for t in range(0, 8000, 50)]
        self.assertEqual(kinds(frames), ["lift", "putdown"])

    def test_ignores_frames_without_imu_or_time(self):
        d = GestureDetector()
        self.assertEqual(d.feed({"type": "telemetry"}), [])
        self.assertEqual(d.feed({"type": "telemetry", "uptime_ms": 0, "imu": {"ok": False}}), [])


if __name__ == "__main__":
    unittest.main()
