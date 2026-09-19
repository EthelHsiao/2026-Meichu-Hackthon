# AI-PC Work Progress Collector

This agent runs on an Ubuntu desktop, collects universal desktop context, and sends selected observations plus screenshots to a VLM endpoint. The endpoint is configured with `MI300_API` and `MI300_OBSERVATION_PATH` and returns only a short description `{"text": ..., "error": ... | null}`. The agent writes that description into the local memory database (`memory/`, see `../docs/memory.md`); timing, merging and embeddings are handled locally, not by the VLM.

## What it collects

Every local poll collects:

- foreground application and window title
- running process names
- idle seconds

Screenshots are captured every 30 seconds by default and also when the foreground app/window changes. A VLM request is sent only for meaningful changes and never more often than once per 60 seconds by default. The first observation is submitted immediately.

Git, VS Code, browser, and terminal metadata are optional future enrichers. They are not required for Word, PowerPoint, LeetCode, Photoshop, meetings, or other applications. Raw keyboard and mouse input are never collected.

## Ubuntu prerequisites

Install the desktop command-line utilities and Python dependencies:

```bash
sudo apt install xdotool xprintidle x11-utils procps
python3 -m pip install -r requirements.txt
```

The desktop session must expose X11-compatible `xdotool`, `xprop`, and `xprintidle` commands. If a utility is unavailable, its fields become `null` and the collector continues.

## Configuration

```bash
export MI300_API=http://localhost:8000
export MI300_OBSERVATION_PATH=/observations
export LOCAL_POLL_SECONDS=10
export SCREENSHOT_SECONDS=30
export MIN_VLM_SECONDS=60
export IDLE_THRESHOLD_SECONDS=60
export SCREENSHOT_DIR=./screenshots
export RETRY_QUEUE_SIZE=20
python3 screen_watcher.py
```

For an SSH-forwarded MI300 service:

```bash
ssh -N -L 8000:localhost:8000 mi300
```

The local retry queue is bounded. A failed request does not stop polling; the oldest pending item is dropped when the queue is full. Screenshots are written to `SCREENSHOT_DIR` for the MI300 request and local audit, so configure filesystem permissions and retention appropriately.

## Test without a desktop or MI300

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```
