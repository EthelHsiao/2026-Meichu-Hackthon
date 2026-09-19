# Work Progress Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Ubuntu AI-PC collector that creates universal desktop observations, detects meaningful changes, and sends rate-limited observation-plus-screenshot payloads to the existing MI300 semantic-memory API.

**Architecture:** Keep collection, change detection, transport, and orchestration in focused Python modules under `ai-pc-agent`. The collector uses Linux command adapters and existing `mss`/Pillow dependencies; the transport uses the existing `requests` dependency and a configurable MI300 route. The MI300 API is treated as already implemented and is not modified.

**Tech Stack:** Python 3, standard library, `mss`, Pillow, `requests`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-19-work-progress-tracker-design.md`

## Global Constraints

- Local polling defaults to 10 seconds, screenshot capture to 30 seconds, and minimum VLM submission interval to 60 seconds.
- The universal observation must work without Git, VS Code, browser, or terminal metadata.
- Optional enrichments are nullable and must not make collection fail.
- Raw keyboard and mouse input must never be collected.
- MI300 endpoint URL and route must be configurable; the client must not require Ollama locally.
- Network failure must not stop local collection; retries are bounded.
- Tests must not require a live desktop, network, or MI300 service.

## Review Focus

- A title-only change must not cause a VLM call for trivial clock/status suffix changes; test normalized titles.
- A screenshot must not be sent more often than the configured minimum interval; test coalescing/rate limiting.
- A failed desktop command or optional enricher must produce a nullable field, not terminate the loop; test isolation.
- A failed MI300 request must remain bounded and retryable without blocking future collection; test queue limits.
- A payload must contain no keyboard/mouse fields and must preserve arbitrary-app observations; test contract validation.

### Task 1: Define observation models and validation

**Files:**
- Create: `ai-pc-agent/observation_models.py`
- Create: `ai-pc-agent/tests/test_observation_models.py`

**Interfaces:**
- Produces `ACTIVITY_VALUES`, `build_observation(...)`, `validate_observation(payload)`, and `validate_semantic_memory(payload)` for later collector/client code.

- [ ] **Step 1: Write the failing tests**

```python
class ObservationModelTests(unittest.TestCase):
    def test_build_observation_supports_arbitrary_app_without_enrichments(self):
        payload = build_observation(
            timestamp="2026-09-19T16:30:00+08:00",
            foreground={"app": "libreoffice", "window_title": "Proposal.odt", "workspace": None},
            system={"running_apps": ["libreoffice"], "idle_seconds": 4},
            screen={"screenshot_path": "/tmp/a.jpg", "image_sha256": "abc", "perceptual_hash": "def"},
        )
        self.assertEqual(payload["foreground"]["app"], "libreoffice")
        self.assertIsNone(payload["enrichments"]["git"])
        self.assertNotIn("keyboard", payload)

    def test_invalid_semantic_activity_and_confidence_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_semantic_memory({"activity": "inventing", "confidence": 0.5})
        with self.assertRaises(ValueError):
            validate_semantic_memory({"activity": "coding", "confidence": 2})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest ai-pc-agent.tests.test_observation_models -v`

Expected: FAIL because `observation_models` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement UUID generation, default nullable enrichments, required universal fields, and semantic enum/range validation. Keep validation focused on the contract; do not add model inference or persistence here.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest ai-pc-agent.tests.test_observation_models -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-pc-agent/observation_models.py ai-pc-agent/tests/test_observation_models.py
git commit -m "feat: define work tracker observation contracts"
```

### Task 2: Implement Linux collection adapters

**Files:**
- Create: `ai-pc-agent/collectors.py`
- Create: `ai-pc-agent/tests/test_collectors.py`

**Interfaces:**
- Consumes: `build_observation` from Task 1.
- Produces: `CommandRunner`, `LinuxDesktopCollector.collect()`, and `OptionalEnricher` protocol.

- [ ] **Step 1: Write the failing tests**

```python
class CollectorTests(unittest.TestCase):
    def test_collects_foreground_idle_and_processes_from_fixture_commands(self):
        runner = FixtureRunner({
            ("xdotool", "getactivewindow"): "42\n",
            ("xdotool", "getwindowname", "42"): "Proposal.odt — LibreOffice\n",
            ("xprop", "-id", "42", "_NET_WM_PID"): "_NET_WM_PID(CARDINAL) = 123\n",
            ("ps", "-eo", "comm="): "libreoffice\nchrome\n",
            ("xprintidle",): "4000\n",
        })
        state = LinuxDesktopCollector(runner=runner).collect()
        self.assertEqual(state["foreground"]["app"], "libreoffice")
        self.assertEqual(state["foreground"]["window_title"], "Proposal.odt")
        self.assertEqual(state["system"]["idle_seconds"], 4)

    def test_optional_enricher_failure_is_nullable(self):
        state = LinuxDesktopCollector(runner=FailingRunner()).collect()
        self.assertIsNone(state["enrichments"]["git"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest ai-pc-agent.tests.test_collectors -v`

Expected: FAIL because `collectors` does not exist.

- [ ] **Step 3: Write minimal implementation**

Use `xdotool`, `xprop`, `xprintidle`, and `ps` through an injectable runner. Normalize the focused window title to remove a trailing application suffix and derive the app from the focused process when possible. Treat missing Linux utilities as nullable state. Do not read keyboard or mouse events.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest ai-pc-agent.tests.test_collectors -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-pc-agent/collectors.py ai-pc-agent/tests/test_collectors.py
git commit -m "feat: collect universal Linux desktop state"
```

### Task 3: Add screenshot capture and change detection

**Files:**
- Create: `ai-pc-agent/screenshot.py`
- Create: `ai-pc-agent/detector.py`
- Create: `ai-pc-agent/tests/test_detector.py`

**Interfaces:**
- Produces: `ScreenshotCapture.capture()`, `normalize_title(title)`, `ChangeDetector.should_submit(...)`, and `ChangeDetector.mark_submitted(...)`.

- [ ] **Step 1: Write the failing tests**

```python
class DetectorTests(unittest.TestCase):
    def test_trivial_title_suffix_change_does_not_trigger(self):
        detector = ChangeDetector(min_vlm_seconds=60)
        old = state("code", "main.py — VS Code", idle=2, phash="aaaa")
        new = state("code", "main.py — VS Code • 1", idle=2, phash="aaaa")
        self.assertFalse(detector.should_submit(old, new, now=100))

    def test_foreground_change_triggers_and_minimum_interval_is_respected(self):
        detector = ChangeDetector(min_vlm_seconds=60)
        old = state("code", "main.py", idle=2, phash="aaaa")
        new = state("chrome", "LeetCode", idle=2, phash="bbbb")
        self.assertTrue(detector.should_submit(old, new, now=100))
        detector.mark_submitted(new, now=100)
        self.assertFalse(detector.should_submit(new, state("chrome", "LeetCode", 2, "cccc"), now=130))
        self.assertTrue(detector.should_submit(new, state("chrome", "LeetCode", 2, "cccc"), now=161))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest ai-pc-agent.tests.test_detector -v`

Expected: FAIL because `detector` does not exist.

- [ ] **Step 3: Write minimal implementation**

Capture resized JPEGs through the existing `mss` and Pillow dependencies, calculate SHA-256 and a small average perceptual hash, and compare normalized universal state. Permit immediate submission for meaningful foreground/idle/enricher changes only when the minimum VLM interval allows it; allow the first observation immediately.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest ai-pc-agent.tests.test_detector -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-pc-agent/screenshot.py ai-pc-agent/detector.py ai-pc-agent/tests/test_detector.py
git commit -m "feat: detect meaningful desktop changes"
```

### Task 4: Add bounded MI300 transport and orchestration

**Files:**
- Create: `ai-pc-agent/mi300_client.py`
- Create: `ai-pc-agent/agent.py`
- Modify: `ai-pc-agent/screen_watcher.py`
- Modify: `ai-pc-agent/requirements.txt`
- Create: `ai-pc-agent/tests/test_agent.py`
- Create: `ai-pc-agent/tests/test_mi300_client.py`

**Interfaces:**
- Consumes: collector state, screenshot capture, detector, and observation validators.
- Produces: `MI300Client.submit_observation(payload, image_bytes)`, `BoundedRetryQueue`, and `WorkProgressAgent.run_once(now=None)`.

- [ ] **Step 1: Write the failing tests**

```python
class ClientTests(unittest.TestCase):
    def test_posts_observation_and_image_to_configured_route(self):
        transport = RecordingTransport(response={"memory_id": "m1", "activity": "writing"})
        client = MI300Client("http://mi300:8000", "/observations", transport=transport)
        result = client.submit_observation({"observation_id": "o1"}, b"jpeg")
        self.assertEqual(result["memory_id"], "m1")
        self.assertEqual(transport.path, "/observations")

class AgentTests(unittest.TestCase):
    def test_failed_delivery_is_bounded_and_does_not_raise(self):
        queue = BoundedRetryQueue(max_items=2)
        queue.put({"observation_id": "1"})
        queue.put({"observation_id": "2"})
        queue.put({"observation_id": "3"})
        self.assertEqual(queue.size(), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest ai-pc-agent.tests.test_mi300_client ai-pc-agent.tests.test_agent -v`

Expected: FAIL because the transport and agent modules do not exist.

- [ ] **Step 3: Write minimal implementation**

Implement a configurable HTTP client that sends JSON metadata plus base64 JPEG to `MI300_API` and `MI300_OBSERVATION_PATH`, validates the returned semantic memory, and raises a retryable error on HTTP/network failures. Implement a bounded deque queue and a single-step agent that collects state, captures a screenshot on schedule, submits only detector-approved observations, and continues after individual failures.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s ai-pc-agent/tests -v`

Expected: PASS for all AI-PC tests.

- [ ] **Step 5: Commit**

```bash
git add ai-pc-agent/mi300_client.py ai-pc-agent/agent.py ai-pc-agent/screen_watcher.py ai-pc-agent/requirements.txt ai-pc-agent/tests
git commit -m "feat: send rate-limited observations to MI300"
```

### Task 5: Document configuration and run the full verification suite

**Files:**
- Modify: `ai-pc-agent/README.md`
- Create: `ai-pc-agent/tests/__init__.py`

- [ ] **Step 1: Write the failing documentation/configuration test**

Add a test that imports the configuration defaults and asserts the documented values are 10, 30, 60, and 60 seconds.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s ai-pc-agent/tests -v`

Expected: FAIL if defaults or configuration exports are missing.

- [ ] **Step 3: Write minimal implementation/documentation**

Expose environment variables for the four timing values, MI300 URL/path, screenshot directory, screenshot retention, and queue size. Document Linux prerequisites (`xdotool`, `xprop`, `xprintidle`, `ps`), privacy defaults, operation, and an example SSH-forwarded MI300 URL. Keep the existing `send_note` helper behavior documented if retained.

- [ ] **Step 4: Run the full test suite**

Run: `python -m unittest discover -s ai-pc-agent/tests -v && python -m compileall -q ai-pc-agent`

Expected: PASS with zero test failures and compileall exit code 0.

- [ ] **Step 5: Commit**

```bash
git add ai-pc-agent/README.md ai-pc-agent/tests/__init__.py ai-pc-agent
git commit -m "docs: document AI PC work tracker configuration"
```
