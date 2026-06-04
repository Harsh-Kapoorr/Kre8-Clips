import json
import os
import time
from typing import Callable, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text

console = Console()


STEP_LABELS = {
    1: "Validating",
    2: "Downloading",
    3: "Extracting Audio",
    4: "Transcribing",
    5: "Analyzing",
    6: "Generating Clips",
    7: "Complete",
}


# Cap the extrapolated ETA so a stalled or unusually slow first step doesn't
# project hours of remaining work onto the UI.
MAX_ETA_SECONDS: float = 300.0
# Don't extrapolate from samples below this elapsed-time floor; the (elapsed /
# progress) formula is meaningless when both numbers are near zero.
_ETA_MIN_ELAPSED_SECONDS: float = 2.0


_progress_sink: Optional[str] = None
_progress_sink_warned: bool = False
_job_started_at: Optional[float] = None
_last_step_started_at: Optional[float] = None

# Indirected so tests can swap in a deterministic clock without sleeping.
_time_fn: Callable[[], float] = time.monotonic


def set_progress_sink(path: Optional[str]) -> None:
    """Set the sidecar file that receives structured progress events.

    Pass ``None`` to clear the sink. When set, :func:`print_step` appends a
    JSON object per step so the Next.js API route can read the latest line
    instead of parsing Rich console output with regex.

    Setting a new sink also resets the per-job timing baseline so the next
    event's ``elapsed_s`` / ``eta_s`` start from zero rather than carrying
    state from a previous run.
    """
    global _progress_sink, _progress_sink_warned
    global _job_started_at, _last_step_started_at
    _progress_sink = path
    # Reset the warning latch so a new sink can warn about its own failures.
    _progress_sink_warned = False
    # New job = fresh timing baseline.
    _job_started_at = None
    _last_step_started_at = None


def _compute_timing(progress: float) -> dict:
    """Return the timing fields attached to each progress event.

    Lazily initialises the job baseline on the first call after the sink is
    set, then derives ``elapsed_s`` and a remaining-time estimate using the
    self-correcting formula ``elapsed * (1/progress - 1)``. The estimate is
    capped at :data:`MAX_ETA_SECONDS` so a single slow or stalled step can't
    project hours of fake remaining time to the UI.
    """
    global _job_started_at, _last_step_started_at
    now = _time_fn()
    if _job_started_at is None:
        _job_started_at = now
    elapsed = max(0.0, now - _job_started_at)
    last_step_duration: Optional[float] = None
    if _last_step_started_at is not None:
        last_step_duration = max(0.0, now - _last_step_started_at)
    _last_step_started_at = now

    eta: Optional[float] = None
    if progress >= 1.0:
        eta = 0.0
    elif progress > 0.0 and elapsed >= _ETA_MIN_ELAPSED_SECONDS:
        raw = elapsed * (1.0 / progress - 1.0)
        if raw > 0.0:
            eta = min(MAX_ETA_SECONDS, raw)

    return {
        "elapsed_s": round(elapsed, 3),
        "step_started_at_s": round(now - _job_started_at, 3),
        "last_step_duration_s": (
            None if last_step_duration is None else round(last_step_duration, 3)
        ),
        "eta_s": None if eta is None else round(eta, 3),
        "eta_capped": eta is not None and eta >= MAX_ETA_SECONDS,
    }


def _write_progress(step: str, progress: float, step_detail: str = "") -> None:
    """Append a structured progress event to the active sink (if any)."""
    global _progress_sink_warned
    if not _progress_sink:
        return
    # Compute timing outside the OSError-swallowing block: arithmetic on the
    # monotonic clock should never raise, and we want any real bug here to be
    # noisy rather than silently disabled.
    timing = _compute_timing(progress)
    try:
        payload = json.dumps({
            "step": step,
            "progress": progress,
            "step_detail": step_detail,
            **timing,
        })
        fd = os.open(_progress_sink, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (payload + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        # Log only the first failure per sink so we don't spam the console
        # if .jobs/ becomes unwritable during a long run.
        if not _progress_sink_warned:
            _progress_sink_warned = True
            console.print(
                f"[dim yellow]progress sidecar write failed: {exc}; "
                f"frontend will fall back to regex parsing[/dim yellow]"
            )


def create_progress_bar(description: str) -> Progress:
    """Create a styled progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    )


def print_step(step_num: int, total: int, message: str, emoji: str = "→"):
    """Print a step header and emit a structured progress event."""
    console.print(f"\n[bold violet][{step_num}/{total}][/bold violet] {emoji} {message}")
    label = STEP_LABELS.get(step_num, message)
    progress = (step_num - 0.5) / total if total > 0 else 0.0
    _write_progress(label, progress, message)


def print_success(message: str):
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str):
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[bold amber]![/bold amber] {message}")


def print_info(message: str):
    """Print an info message."""
    console.print(f"[bold cyan]ℹ[/bold cyan] {message}")


def print_header(title: str):
    """Print a header banner."""
    border = "═" * (len(title) + 4)
    console.print(f"\n╔{border}╗")
    console.print(f"║  {title}  ║")
    console.print(f"╚{border}╝\n")