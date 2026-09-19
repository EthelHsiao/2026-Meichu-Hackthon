# Low-latency ROCm STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local Breeze-ASR service select and validate AMD ROCm GPU execution explicitly, tune the live path for one-stream latency, and provide repeatable CPU-vs-ROCm measurements.

**Architecture:** Keep the existing long-lived Transformers runtime and WebSocket protocol. Centralize device resolution/validation so `rocm` maps to PyTorch `cuda:0`, `auto` prefers HIP only when usable, and explicit GPU requests never silently fall back to CPU. Add a dependency-light WAV benchmark that warms the same runtime and reports JSON latency metrics.

**Tech Stack:** Python 3.12, FastAPI, PyTorch/ROCm, Transformers 4.44.2, NumPy, pytest, standard-library `wave`/`argparse`/`json`.

**Spec:** `docs/superpowers/specs/2026-09-19-low-latency-rocm-stt-design.md`

## Global Constraints

- Preserve CPU fallback and the existing WebSocket message protocol.
- `ASR_DEVICE=rocm` means AMD ROCm/HIP and resolves to `cuda:0`.
- GPU inference uses `float16`; CPU keeps the existing BF16/FP32 choice.
- Do not install system ROCm packages or alter drivers/groups.
- Do not add NPU/XDNA support in this change.

## Review Focus

- A CUDA-only torch build with `ASR_DEVICE=rocm` must fail clearly instead of silently using CPU; test in Task 1.
- A HIP build with no visible device must fail for explicit `rocm`; test in Task 1.
- `ASR_DEVICE=auto` must remain CPU-safe on ordinary environments; test in Task 1.
- Diagnostics must not query a device name when CUDA/HIP is unavailable; test in Task 2.
- A short/empty WAV must produce valid benchmark JSON without a divide-by-zero; test in Task 3.

### Task 1: Centralize and test accelerator resolution

**Files:**
- Create: `stt/backend/test_main.py`
- Modify: `stt/backend/main.py:38-78` (device constants and resolver)

**Interfaces:**
- Produces `resolve_device(torch_module) -> torch.device` and `validate_accelerator(torch_module, device, requested_mode) -> None` for runtime loading and tests.

- [ ] **Step 1: Write the failing tests**

```python
def test_rocm_requires_hip_and_selects_cuda_zero():
    torch = fake_torch(hip="6.4", available=True)
    assert str(resolve_device(torch, "rocm")) == "cuda:0"

def test_rocm_rejects_cuda_only_build():
    torch = fake_torch(hip=None, cuda="13.0", available=True)
    with pytest.raises(RuntimeError, match="ROCm/HIP"):
        resolve_device(torch, "rocm")

def test_auto_uses_cpu_without_accelerator():
    torch = fake_torch(hip=None, cuda=None, available=False)
    assert str(resolve_device(torch, "auto")) == "cpu"

def test_rocm_rejects_unavailable_device():
    torch = fake_torch(hip="6.4", available=False)
    with pytest.raises(RuntimeError, match="available"):
        resolve_device(torch, "rocm")
```

The fake module only needs `version.hip`, `version.cuda`, `cuda.is_available()`, and `device(name)`; construct it inside the test file so tests do not import or install torch.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest -q stt/backend/test_main.py`

Expected: FAIL because the current resolver accepts only the process-global setting and does not validate ROCm.

- [ ] **Step 3: Implement the minimal resolver**

Replace the global-only resolver with a mode-parameterized function. Normalize `"rocm"` and `"cuda"` to the accelerator path, require `torch.version.hip` for `rocm`, require `torch.cuda.is_available()` for explicit accelerator modes, and use CPU for `auto` when no accelerator is available. Keep `auto` HIP/CUDA agnostic after availability is established.

- [ ] **Step 4: Update runtime loading to use validation**

Call `resolve_device(torch, ASR_DEVICE)` from `load_runtime`; retain `float16` for any non-CPU device and the current CPU BF16 detection. Include the detected HIP/CUDA build in explicit-request error text.

- [ ] **Step 5: Run focused and existing checks**

Run: `pytest -q stt/backend/test_main.py` and `python -m py_compile stt/backend/main.py`

Expected: all resolver tests pass and compilation succeeds.

- [ ] **Step 6: Commit**

```bash
git add stt/backend/main.py stt/backend/test_main.py
git commit -m "feat: validate ROCm device selection"
```

### Task 2: Expose accelerator diagnostics and low-latency defaults

**Files:**
- Modify: `stt/backend/main.py:14-25,125-160,200-225`
- Modify: `stt/README.md` (ROCm and latency configuration)
- Test: `stt/backend/test_main.py`

**Interfaces:**
- `/diagnostics` returns `accelerator`, `torch_hip`, `torch_cuda_build`, and safe availability/device fields.
- Existing `/healthz` retains its response keys and reports the selected dtype/device.

- [ ] **Step 1: Add failing diagnostics tests**

Test the pure diagnostics helper (extracted as `torch_diagnostics(torch_module, setting)`) with unavailable and available fake torch modules. Assert unavailable returns `torch_device is None` and never invokes `get_device_name`; assert HIP available reports `accelerator == "rocm"`.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest -q stt/backend/test_main.py -k diagnostics`

Expected: FAIL because diagnostics currently has no accelerator classification and directly embeds device probing.

- [ ] **Step 3: Implement safe diagnostics and tuned defaults**

Extract guarded diagnostics logic, classify HIP as `rocm`, and only call `get_device_name(0)` after `is_available()` is true. Adjust draft window/interval defaults to the approved low-latency values while preserving both environment overrides. Do not alter message names or payload compatibility.

- [ ] **Step 4: Update README instructions**

Document `ASR_DEVICE=rocm`, the explicit no-silent-fallback behavior, and the latency variables. Keep the existing ROCm wheel and `check_env` instructions; state that `cuda:0` is the PyTorch device spelling for ROCm.

- [ ] **Step 5: Run tests and compile checks**

Run: `pytest -q stt/backend/test_main.py` and `python -m py_compile stt/backend/main.py`.

- [ ] **Step 6: Commit**

```bash
git add stt/backend/main.py stt/backend/test_main.py stt/README.md
git commit -m "feat: expose ROCm diagnostics and latency tuning"
```

### Task 3: Add a warm WAV latency benchmark

**Files:**
- Create: `stt/backend/benchmark.py`
- Modify: `stt/backend/test_main.py`
- Modify: `stt/README.md`

**Interfaces:**
- CLI: `python -m backend.benchmark path/to/input.wav --device rocm --runs 3`
- Output: one JSON object containing `device`, `dtype`, `runs`, `median_latency_ms`, `p95_latency_ms`, and `real_time_factor`.

- [ ] **Step 1: Write failing benchmark tests**

```python
def test_percentile_and_rtf_handle_zero_length_audio():
    result = summarize_latencies([], audio_seconds=0.0)
    assert result["runs"] == 0
    assert result["real_time_factor"] is None

def test_benchmark_parser_requires_existing_wav(tmp_path):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([str(tmp_path / "missing.wav")])
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest -q stt/backend/test_main.py -k benchmark`

Expected: FAIL because `benchmark.py` and its helpers do not exist.

- [ ] **Step 3: Implement benchmark helpers and CLI**

Read mono/PCM WAV data with `wave`, load the same `load_runtime()` used by the server after setting the requested `ASR_DEVICE`, run one warm-up decode, then run the requested number of timed decodes. Compute median, p95, and real-time factor with `None` for no audio/runs. Print exactly one JSON result to stdout; logs may remain on stderr.

- [ ] **Step 4: Run focused tests and a syntax check**

Run: `pytest -q stt/backend/test_main.py -k benchmark` and `python -m py_compile stt/backend/benchmark.py`.

- [ ] **Step 5: Document the benchmark command**

Add CPU and ROCm example commands and explain that both runs must use the same WAV and a warmed runtime. Record median latency and real-time factor, without claiming a speedup until run on the target host.

- [ ] **Step 6: Commit**

```bash
git add stt/backend/benchmark.py stt/backend/test_main.py stt/README.md
git commit -m "feat: add warmed STT latency benchmark"
```

### Task 4: Full verification and handoff

**Files:**
- Modify: none unless verification exposes a defect.

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -q` from the repository root.

Expected: all tests pass. If no pre-existing suite exists, the new resolver/diagnostics/benchmark tests are the complete suite.

- [ ] **Step 2: Run environment classification**

Run: `stt/.venv-rocm/bin/python stt/backend/check_env.py` when the ROCm environment is present. Report whether this host has a usable HIP torch build; do not install system packages automatically.

- [ ] **Step 3: Run target-host benchmark when possible**

Run the documented CPU and `ASR_DEVICE=rocm` benchmark commands against the same existing WAV sample. Report measured median latency and real-time factor, or clearly state that hardware execution was unavailable.

- [ ] **Step 4: Review final diff and status**

Run: `git diff --check` and `git status --short`.

- [ ] **Step 5: Commit any verification-only fixes**

Use a focused commit message describing the observed defect and its test if a fix is required; otherwise leave the implementation commits intact.
