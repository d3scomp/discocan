"""Reusable RichLog panel for showing CAN traffic.

The pause/autoscroll bindings live at App level (see DiscocanApp.BINDINGS) so
the footer hints stay visible regardless of which tab is active and so the
toggle applies uniformly to every TracePanel in the DOM.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import RichLog


def _format_fw_timestamp(fw_ms: int | None) -> str:
    """Format a firmware HAL_GetTick() value as HH:MM:SS.mmm (boot-relative)."""
    if fw_ms is None:
        return "  --:--:--.---"
    total_s, ms = divmod(int(fw_ms) & 0xFFFFFFFF, 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


class TracePanel(Horizontal):
    """RichLog with externally-driven pause and autoscroll state."""

    DEFAULT_CSS = """
    TracePanel {
        height: 100%;
        min-width: 25;
    }
    TracePanel > RichLog {
        width: 1fr;
        height: 100%;
        border: solid $primary;
    }
    """

    def __init__(self, startup_msg: str = "", **kwargs):
        super().__init__(**kwargs)
        self._paused = False
        self._startup_msg = startup_msg

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, wrap=False, max_lines=300)

    def on_mount(self) -> None:
        if self._startup_msg:
            self.query_one(RichLog).write(self._startup_msg)

    # ── Public ────────────────────────────────────────────────────────────────

    def log_entry(
        self,
        direction: str,
        fw_timestamp_ms: int | None,
        arb_id: int,
        dlc: int,
        data: list[int],
    ) -> None:
        if self._paused:
            return
        log = self.query_one(RichLog)
        ts = _format_fw_timestamp(fw_timestamp_ms)
        hex_data = " ".join(f"{b:02X}" for b in data)
        color = "green" if direction == "rx" else "cyan"
        log.write(
            f"[{color}]{direction.upper()}[/{color}] {ts}  "
            f"[b]0x{arb_id:03X}[/b]  DLC={dlc}  [{hex_data}]"
        )

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def set_autoscroll(self, autoscroll: bool) -> None:
        self.query_one(RichLog).auto_scroll = autoscroll
