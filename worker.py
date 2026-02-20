"""
worker.py — TubeWise Background Worker Daemon
================================================
Processes jobs from the SQLite queue in the background.

ARCHITECTURE:
  tubewise --worker start  → start_daemon() → subprocess.Popen → _run_daemon()
  tubewise --worker stop   → stop_daemon() → SIGTERM to daemon PID
  tubewise --worker status → reads worker_state from queue.db

  run_worker() polls the queue every POLL_INTERVAL seconds.
  When a pending job is found, it's dispatched to a ProcessPoolExecutor
  for parallel processing (configurable worker count).

DAEMON LIFECYCLE:
  start_daemon()
    ├── Checks for existing daemon (prevents duplicates)
    ├── subprocess.Popen to spawn fresh daemon process
    └── Parent returns immediately after printing status

  _run_daemon() [runs in the subprocess]
    ├── os.setsid() to detach from terminal
    ├── Redirects stdout/stderr to log file
    ├── Registers SIGTERM/SIGINT handlers for graceful shutdown
    ├── Creates fresh QueueManager (new SQLite connection)
    └── Calls run_worker()

  stop_daemon()
    ├── Reads PID from worker_state table
    ├── Sends SIGTERM to the daemon
    └── Updates worker_state to 'stopped'

CONCURRENCY:
  Jobs are claimed atomically in SQLite (UPDATE WHERE id = subquery).
  ProcessPoolExecutor handles parallel execution of multiple jobs.
  Each worker process runs process_single_job() independently.

MACOS FORK SAFETY:
  On macOS ARM64 (Apple Silicon), os.fork() causes SIGSEGV because
  forking copies the parent's corrupted C-library state:
    - OpenBLAS thread pool (NumPy) → crash in libopenblas64_.0.dylib
    - SQLite/os_log tracing       → crash in libsystem_trace.dylib

  We avoid fork entirely in two places:
    1. DAEMON: subprocess.Popen (fork+exec) instead of os.fork().
       The exec() replaces the memory image before any library code
       runs, giving the daemon a completely clean process state.
    2. WORKERS: ProcessPoolExecutor uses "forkserver" start method.
       The forkserver process is spawned before heavy libraries load,
       and subsequent workers are forked from that clean state.
    3. OPENBLAS_NUM_THREADS=1 is set before any imports as an extra
       safety measure to disable OpenBLAS multi-threading.
"""

from __future__ import annotations

# ── macOS fork safety: disable OpenBLAS threading BEFORE any imports ──
# NumPy bundles libopenblas64_ which uses pthreads internally. On macOS
# ARM64 (Apple Silicon), forking a process after OpenBLAS has created its
# thread pool causes SIGSEGV (EXC_BAD_ACCESS in libopenblas64_.0.dylib).
# Setting this env var to "1" tells OpenBLAS to run single-threaded,
# which avoids the fork-unsafe thread state entirely.
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys
import signal
import time
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, Future
from datetime import datetime
from pathlib import Path

from config import Config

logger = logging.getLogger("tubewise.worker")

# How often (seconds) the worker checks for new jobs
POLL_INTERVAL = 3

# Flag for graceful shutdown
_shutdown_requested = False


def process_single_job(job: dict) -> dict:
    """
    Run the full TubeWise pipeline for a single queued job.

    This function is the top-level callable for ProcessPoolExecutor.
    It must be importable at module level (not a nested function or lambda).

    Each worker process:
      1. Sets up its own logging
      2. Extracts transcript
      4. Generates summary via Bedrock
      5. Saves locally + publishes to Notion

    Args:
        job: Dict from the queue with keys: id, url, language, no_notion, source

    Returns:
        Dict with: job_id, status ("completed" or "failed"),
                   notion_url, local_file, error
    """
    from logging_config import setup_logging
    setup_logging(level=Config.LOG_LEVEL, log_file=Config.LOG_FILE_PATH)

    job_id = job["id"]
    url = job["url"]
    language = job.get("language", "en")
    no_notion = bool(job.get("no_notion", 0))

    logger.info(f"[Job #{job_id}] Processing: {url}")

    try:
        from transcript import fetch_video_info
        from summarizer import generate_summary
        from agent import save_local_output
        from notion_publisher import publish_to_notion

        # ── Step 1: Extract content ──
        content = fetch_video_info(url, language)

        # ── Step 2: Generate summary ──
        raw_summary = generate_summary(content)

        # ── Step 3: Save locally ──
        local_file = save_local_output(raw_summary, content.title)

        # ── Step 4: Publish to Notion ──
        notion_url = ""
        if not no_notion:
            notion_url = publish_to_notion(
                raw_summary=raw_summary,
                video_url=content.url,
                video_title=content.title,
                channel=content.creator,
                duration=content.duration_formatted,
                word_count=content.word_count,
            )

        logger.info(f"[Job #{job_id}] Completed successfully")
        return {
            "job_id": job_id,
            "status": "completed",
            "notion_url": notion_url,
            "local_file": local_file,
            "error": "",
        }

    except Exception as e:
        logger.error(f"[Job #{job_id}] Failed: {e}")
        return {
            "job_id": job_id,
            "status": "failed",
            "notion_url": "",
            "local_file": "",
            "error": str(e),
        }


def _get_safe_mp_context() -> multiprocessing.context.BaseContext:
    """
    Return a multiprocessing context that is safe for macOS ARM64.

    On macOS, the default "fork" start method copies the parent process's
    memory including thread state from libraries like OpenBLAS (bundled in
    NumPy). This corrupted state causes SIGSEGV in the child process.

    Start method selection depends on whether we're running as a frozen
    binary (PyInstaller) or as a Python script:

      - FROZEN BINARY: Use "spawn". The "forkserver" and "spawn" methods
        both work with freeze_support(), but "forkserver" has known issues
        on POSIX frozen executables (CPython docs explicitly warn about this).
        "spawn" is the safest — it's the default on macOS and fully supported
        by PyInstaller's freeze_support() override.

      - PYTHON SCRIPT: Use "forkserver". It's faster than "spawn" because it
        forks from a clean server process instead of re-importing everything.
        No freeze_support() needed.

    Falls back to "fork" only if nothing else is available (shouldn't happen
    on Python 3.9+ / macOS / Linux).

    Returns:
        A multiprocessing context using the safest available start method.
    """
    is_frozen = getattr(sys, "frozen", False)
    available = multiprocessing.get_all_start_methods()

    if is_frozen:
        # Frozen binary: "spawn" is safest — fully supported by PyInstaller
        if "spawn" in available:
            return multiprocessing.get_context("spawn")
    else:
        # Python script: "forkserver" is faster and fork-safe
        if "forkserver" in available:
            return multiprocessing.get_context("forkserver")

    # Fallback — "fork" is always available on Unix
    return multiprocessing.get_context("fork")


def run_worker(worker_count: int) -> None:
    """
    Main worker loop — polls the queue and dispatches jobs to a pool.

    Runs indefinitely until SIGTERM/SIGINT is received.

    Args:
        worker_count: Max number of parallel workers in the pool
    """
    global _shutdown_requested

    from queue_manager import QueueManager

    qm = QueueManager()

    # Reset any jobs stuck in 'processing' from a previous crashed worker
    reset_count = qm.reset_stale_jobs()
    if reset_count:
        logger.info(f"Reset {reset_count} stale job(s) from previous run")

    logger.info(f"Worker started (PID: {os.getpid()}, {worker_count} workers)")

    # ── Use forkserver to avoid macOS fork-safety crashes ──
    # The default "fork" start method copies the parent's entire memory space,
    # including any multi-threaded library state (like OpenBLAS). On macOS
    # ARM64 this causes SIGSEGV. "forkserver" spawns a clean server process
    # early, and workers are forked from that clean state instead.
    mp_context = _get_safe_mp_context()
    executor = ProcessPoolExecutor(max_workers=worker_count, mp_context=mp_context)
    active_futures: dict[Future, int] = {}  # future -> job_id

    try:
        while not _shutdown_requested:
            # ── Check completed futures ──
            done_futures = [f for f in active_futures if f.done()]
            for future in done_futures:
                job_id = active_futures.pop(future)
                try:
                    result = future.result()
                    if result["status"] == "completed":
                        qm.mark_completed(
                            job_id,
                            notion_url=result.get("notion_url", ""),
                            local_file=result.get("local_file", ""),
                        )
                        logger.info(f"[Job #{job_id}] Marked completed")
                    else:
                        qm.mark_failed(job_id, result.get("error", "Unknown error"))
                        logger.error(f"[Job #{job_id}] Marked failed: {result.get('error')}")
                except Exception as e:
                    qm.mark_failed(job_id, str(e))
                    logger.error(f"[Job #{job_id}] Worker exception: {e}")

            # ── Submit new jobs if pool has capacity ──
            while len(active_futures) < worker_count:
                job = qm.get_next_pending()
                if job is None:
                    break  # No more pending jobs

                job_id = job["id"]
                logger.info(f"[Job #{job_id}] Dispatching to worker pool")
                future = executor.submit(process_single_job, job)
                active_futures[future] = job_id

            # ── Wait before polling again ──
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    finally:
        logger.info("Shutting down worker pool...")
        executor.shutdown(wait=True, cancel_futures=False)

        # Mark any remaining processing jobs as failed
        for future, job_id in active_futures.items():
            if not future.done():
                qm.mark_failed(job_id, "Worker shutdown while processing")

        logger.info("Worker stopped")


def _signal_handler(signum: int, frame) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info(f"Received signal {signum}, shutting down gracefully...")


def _run_daemon(worker_count: int) -> None:
    """
    Entry point for the daemon subprocess.

    This function runs in a completely fresh Python process spawned by
    start_daemon() via subprocess.Popen. Because it's a new process
    (not a fork), there's no inherited library state from the parent —
    no corrupted OpenBLAS threads, no stale SQLite/os_log handles.

    Invoked two ways depending on how TubeWise runs:
      - Script mode:  python -c "from worker import _run_daemon; _run_daemon(N)"
      - Binary mode:  tubewise --_daemon N  (agent.py intercepts and calls this)

    Args:
        worker_count: Number of parallel workers
    """
    # NOTE: No os.setsid() here — the parent's subprocess.Popen already
    # passes start_new_session=True, which creates a new session for us.
    # Calling setsid() again would fail with PermissionError since the
    # process is already a session leader.

    # ── Redirect stdout/stderr to log file FIRST ──
    # This must happen before any logging setup or print statements.
    # In daemon mode, there's no terminal — stdout/stderr must go to a file
    # or the daemon's output is lost. We capture crashes early by wrapping
    # everything in a try/except that writes to this log file.
    log_path = Config.LOG_FILE_PATH
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_path, "a", encoding="utf-8")

    try:
        os.dup2(log_fd.fileno(), sys.stdout.fileno())
        os.dup2(log_fd.fileno(), sys.stderr.fileno())

        # Set up logging for the daemon
        from logging_config import setup_logging
        setup_logging(level="DEBUG", log_file=Config.LOG_FILE_PATH)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Create a FRESH QueueManager (new SQLite connection, no inherited state)
        from queue_manager import QueueManager
        qm = QueueManager()
        qm.set_worker_state(os.getpid(), "running", worker_count)

        try:
            run_worker(worker_count)
        finally:
            qm.set_worker_state(0, "stopped", worker_count)

    except Exception as e:
        # If anything crashes during daemon startup, write it to the log
        # so it's not silently swallowed. Without this, the daemon dies
        # and the user sees "not running" with no explanation.
        import traceback
        log_fd.write(f"\n[DAEMON CRASH] {datetime.now().isoformat()}\n")
        log_fd.write(f"Error: {e}\n")
        log_fd.write(traceback.format_exc())
        log_fd.write("\n")
        log_fd.flush()
    finally:
        log_fd.close()


def start_daemon(worker_count: int) -> None:
    """
    Start the worker as a background daemon process.

    IMPORTANT — WHY subprocess.Popen INSTEAD OF os.fork():
      On macOS ARM64 (Apple Silicon), os.fork() copies the parent's
      entire process memory, including internal state from C libraries:
        - OpenBLAS thread pool (NumPy) → SIGSEGV in libopenblas64_
        - SQLite/os_log tracing state → SIGSEGV in libsystem_trace
      These are NOT Python-level issues — they're C-level fork-safety
      bugs in macOS system libraries that cannot be fixed with env vars.

      subprocess.Popen spawns a completely fresh process (fork+exec),
      which starts with clean library state. The exec() call replaces
      the forked memory image before any library code runs, avoiding
      all fork-safety issues.

    The daemon PID and status are stored in the SQLite worker_state table.

    Args:
        worker_count: Number of parallel workers
    """
    import subprocess

    from queue_manager import QueueManager

    qm = QueueManager()
    state = qm.get_worker_state()

    # ── Check for existing daemon ──
    if state and state["status"] == "running" and state["pid"]:
        try:
            os.kill(state["pid"], 0)  # Check if PID is alive
            print(f"Worker already running (PID: {state['pid']})")
            print("Use 'tubewise --worker stop' first")
            return
        except (OSError, ProcessLookupError):
            # Stale PID — previous daemon crashed without cleanup
            pass

    # ── Spawn daemon as a fresh subprocess ──
    # This avoids all fork-safety issues on macOS ARM64. The daemon
    # runs _run_daemon() in a completely new Python process with no
    # inherited library state from this parent process.
    #
    # TWO MODES depending on how TubeWise was invoked:
    #
    # 1. PYTHON SCRIPT: sys.executable is the Python interpreter.
    #    We use `python -c "from worker import _run_daemon; ..."` to
    #    launch the daemon, with sys.path manipulation so the daemon
    #    can find our modules regardless of the working directory.
    #
    # 2. PYINSTALLER BINARY: sys.executable is the frozen binary itself
    #    (e.g., /opt/tubewise/tubewise). The binary doesn't support
    #    `-c` — it always runs agent.py's main(). So instead, we pass
    #    a hidden `--_daemon N` flag that agent.py intercepts early
    #    to call _run_daemon() directly.
    #
    # Detection: PyInstaller sets sys.frozen = True on frozen binaries.
    is_frozen = getattr(sys, "frozen", False)

    if is_frozen:
        # Binary mode: re-invoke ourselves with the hidden --_daemon flag
        cmd = [sys.executable, "--_daemon", str(worker_count)]
    else:
        # Script mode: use Python interpreter with -c
        project_dir = str(Path(__file__).resolve().parent)
        daemon_cmd = (
            f"import sys; sys.path.insert(0, {project_dir!r}); "
            f"from worker import _run_daemon; _run_daemon({worker_count})"
        )
        cmd = [sys.executable, "-c", daemon_cmd]

    # cwd=project_dir ensures module imports work in script mode.
    # For frozen mode, all modules are bundled inside the binary.
    cwd = None if is_frozen else str(Path(__file__).resolve().parent)

    proc = subprocess.Popen(
        cmd,
        # Detach from parent's stdin/stdout/stderr
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Start a new process group so the daemon outlives the parent
        start_new_session=True,
        # Run from the project directory so relative imports work (script mode)
        cwd=cwd,
    )

    # ── Verify the daemon actually started ──
    # The daemon subprocess needs a moment to initialize and write its PID
    # to the worker_state table. Without this check, start_daemon() reports
    # success but the daemon may have crashed silently (e.g., import errors,
    # permission issues, multiprocessing freeze_support problems).
    #
    # We poll for up to 5 seconds, checking both:
    #   1. The subprocess is still alive (proc.poll() is None)
    #   2. The worker_state table shows "running"
    daemon_started = False
    for _ in range(10):
        time.sleep(0.5)

        # Check if subprocess died
        if proc.poll() is not None:
            print(f"❌ Worker daemon failed to start (exit code: {proc.returncode})")
            print(f"   Check log: {Config.LOG_FILE_PATH}")
            return

        # Check if daemon registered itself in the DB
        state = qm.get_worker_state()
        if state and state["status"] == "running" and state["pid"] == proc.pid:
            daemon_started = True
            break

    if daemon_started:
        print(f"Worker daemon started (PID: {proc.pid}, {worker_count} workers)")
        print("Use 'tubewise --status' to monitor jobs")
        print("Use 'tubewise --worker stop' to stop")
    else:
        print(f"⚠️  Worker daemon may not have started properly (PID: {proc.pid})")
        print(f"   Check log: {Config.LOG_FILE_PATH}")
        print("   Use 'tubewise --worker status' to verify")


def stop_daemon() -> None:
    """
    Stop the running worker daemon.

    Reads the daemon PID from the worker_state table and sends SIGTERM.
    """
    from queue_manager import QueueManager

    qm = QueueManager()
    state = qm.get_worker_state()

    if not state or state["status"] != "running" or not state.get("pid"):
        print("No worker is running")
        return

    pid = state["pid"]

    try:
        os.kill(pid, 0)  # Check if alive
    except (OSError, ProcessLookupError):
        print(f"Worker PID {pid} is not running (stale state)")
        qm.set_worker_state(0, "stopped", state.get("worker_count", 2))
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent stop signal to worker (PID: {pid})")

        # Wait briefly for graceful shutdown
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except (OSError, ProcessLookupError):
                break

        qm.set_worker_state(0, "stopped", state.get("worker_count", 2))
        print("Worker stopped")

    except PermissionError:
        print(f"Permission denied stopping PID {pid}. Try: kill {pid}")
    except Exception as e:
        print(f"Error stopping worker: {e}")
