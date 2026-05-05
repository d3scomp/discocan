"""Layout 3: trace panel + punchpress text status (right).

Auto-run state and the HOME→PUNCH state machine live on the server side
(`discocan.punchpress_auto`); this layout just posts a SetPunchpressAuto
message to start/stop and reflects the current state from
`punchpress_auto_run` bus events.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Button, Input, RichLog, Static

from discocan.config import (
    PUNCHPRESS_BORDER_ZONE_MM,
    PUNCHPRESS_COMMAND_CAN_ID,
    PUNCHPRESS_COMMAND_HOME,
    PUNCHPRESS_COMMAND_MOVE_TO,
    PUNCHPRESS_COMMAND_PUNCH_AT,
    PUNCHPRESS_ENCODER_TICKS_PER_MM,
    PUNCHPRESS_WORK_AREA_HEIGHT_MM,
    PUNCHPRESS_WORK_AREA_WIDTH_MM,
)
from discocan.tui.messages import RestartPunchpress, SendFrame, SetPunchpressAuto

from .trace_panel import TracePanel


class PunchpressLayout(Horizontal):
    DEFAULT_CSS = """
    PunchpressLayout > TracePanel {
        width: 1fr;
    }
    PunchpressLayout > #pp-panel {
        width: 64;
        min-width: 60;
        height: 100%;
        padding: 1;
        border-left: tall $panel-darken-2;
    }
    #pp-stats {
        height: auto;
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
    }
    #pp-punch-log {
        height: 1fr;
        border: solid $secondary;
    }
    #pp-input-row, #pp-cmd-row, #pp-extra-row {
        height: auto;
        margin-top: 1;
    }
    #pp-input-row Input, #pp-cmd-row Button, #pp-extra-row Button {
        width: 1fr;
        margin-right: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Sim-side state mirrored from SIM_STATUS USB packets. The values stored
        # here are absolute (sim coord system, includes the border zone). We
        # subtract PUNCHPRESS_BORDER_ZONE_MM at display time so the user sees
        # coordinates relative to the lower-left corner of the safe zone.
        self._x_mm = PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_WIDTH_MM / 2
        self._y_mm = PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_HEIGHT_MM / 2
        self._head_up = True
        self._fail = False
        self._border_top = False
        self._border_bottom = False
        self._border_left = False
        self._border_right = False
        self._punches_count = 0
        self._has_data = False

        # Controller-side state mirrored from 0x203 CAN frames
        self._controller_busy = False
        self._has_controller_status = False

        # Auto-run state — mirrored from server's punchpress_auto_run events.
        self._auto_active = False
        self._auto_index = 0
        self._auto_total = 50

    # ── compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield TracePanel()
        with Vertical(id="pp-panel"):
            yield Static(self._stats_text(), id="pp-stats", markup=True)
            yield RichLog(id="pp-punch-log", highlight=False, markup=False, wrap=False, max_lines=300)
            with Horizontal(id="pp-input-row"):
                yield Input(placeholder="X (mm)", id="pp-x")
                yield Input(placeholder="Y (mm)", id="pp-y")
            with Horizontal(id="pp-cmd-row"):
                yield Button("Home", id="pp-home")
                yield Button("Move", id="pp-move")
                yield Button("Punch At", id="pp-punch-at")
            with Horizontal(id="pp-extra-row"):
                yield Button("Sim Restart", id="pp-restart", variant="warning")
                yield Button("Auto Run", id="pp-auto", variant="success")

    # ── rendering ────────────────────────────────────────────────────────────

    def _stats_text(self) -> str:
        if not self._has_data:
            head_label = "[dim]?[/dim]"
            b_str = "[dim](no data)[/dim]"
            pos = "[dim]waiting…[/dim]"
        else:
            if self._fail:
                head_label = "[red b]FAIL[/red b]"
            elif self._head_up:
                head_label = "[green]up[/green]"
            else:
                head_label = "[yellow]DOWN[/yellow]"

            borders = []
            if self._border_top:
                borders.append("[yellow]TOP[/yellow]")
            if self._border_bottom:
                borders.append("[yellow]BOT[/yellow]")
            if self._border_left:
                borders.append("[yellow]LEFT[/yellow]")
            if self._border_right:
                borders.append("[yellow]RIGHT[/yellow]")
            b_str = " ".join(borders) if borders else "[dim](none)[/dim]"
            x_disp = self._x_mm - PUNCHPRESS_BORDER_ZONE_MM
            y_disp = self._y_mm - PUNCHPRESS_BORDER_ZONE_MM
            pos = f"X: {x_disp:7.1f} mm   Y: {y_disp:7.1f} mm"

        if not self._has_controller_status:
            ctrl_label = "[dim]?[/dim]"
        elif self._controller_busy:
            ctrl_label = "[yellow]BUSY[/yellow]"
        else:
            ctrl_label = "[green]idle[/green]"

        if self._auto_active:
            auto_label = (
                f"[cyan]running[/cyan] "
                f"({self._auto_index}/{self._auto_total})"
            )
        else:
            auto_label = "[dim](off)[/dim]"

        return (
            f"[b]Position[/b]   {pos}\n"
            f"[b]Head[/b]       {head_label}\n"
            f"[b]Borders[/b]    {b_str}\n"
            f"[b]Punches[/b]    {self._punches_count}\n"
            f"[b]Controller[/b] {ctrl_label}\n"
            f"[b]Auto run[/b]   {auto_label}"
        )

    def _refresh_stats(self) -> None:
        try:
            self.query_one("#pp-stats", Static).update(self._stats_text())
        except Exception:
            pass

    # ── event sinks ──────────────────────────────────────────────────────────

    def update_status(self, payload: dict) -> None:
        self._x_mm = payload["x"]
        self._y_mm = payload["y"]
        self._head_up = payload["head_up"]
        self._fail = payload["fail"]
        self._border_top = payload["border_top"]
        self._border_bottom = payload["border_bottom"]
        self._border_left = payload["border_left"]
        self._border_right = payload["border_right"]
        self._has_data = True
        self._refresh_stats()

    def add_punch(self, payload: dict) -> None:
        self._punches_count += 1
        # Same convention as in stats: report relative to the safe-zone corner.
        x = payload["x"] - PUNCHPRESS_BORDER_ZONE_MM
        y = payload["y"] - PUNCHPRESS_BORDER_ZONE_MM
        try:
            self.query_one("#pp-punch-log", RichLog).write(
                f"#{self._punches_count:>3}  X={x:7.1f}  Y={y:7.1f} mm"
            )
        except Exception:
            pass
        self._refresh_stats()

    def update_controller_status(self, payload: dict) -> None:
        """Called when a 0x203 frame is decoded by the server."""
        self._has_controller_status = True
        self._controller_busy = bool(payload.get("busy", False))
        self._refresh_stats()

    def update_auto_run(self, payload: dict) -> None:
        """Mirror server-side auto-run state into the layout."""
        self._auto_active = bool(payload.get("active", False))
        self._auto_index = int(payload.get("index", 0))
        self._auto_total = int(payload.get("total", self._auto_total))
        self._refresh_stats()

    def clear_punches(self) -> None:
        self._punches_count = 0
        try:
            self.query_one("#pp-punch-log", RichLog).clear()
        except Exception:
            pass
        self._refresh_stats()

    def log_entry(self, direction: str, fw_timestamp_ms: int | None, arb_id: int, dlc: int, data: list[int]) -> None:
        self.query_one(TracePanel).log_entry(direction, fw_timestamp_ms, arb_id, dlc, data)

    # ── input ────────────────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        # Bare 'r' kept for the original "sim restart" hotkey users were used to.
        if event.key == "r":
            self._send_sim_restart()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "pp-restart":
            self._send_sim_restart()
        elif bid == "pp-home":
            self._send_command(PUNCHPRESS_COMMAND_HOME, 0, 0)
        elif bid == "pp-move":
            self._send_command_with_xy(PUNCHPRESS_COMMAND_MOVE_TO)
        elif bid == "pp-punch-at":
            self._send_command_with_xy(PUNCHPRESS_COMMAND_PUNCH_AT)
        elif bid == "pp-auto":
            self._toggle_auto_sequence()

    # ── command helpers ──────────────────────────────────────────────────────

    def _read_xy_mm(self) -> tuple[float, float] | None:
        x_input = self.query_one("#pp-x", Input)
        y_input = self.query_one("#pp-y", Input)
        if not x_input.value.strip() or not y_input.value.strip():
            self.app.notify("Enter X and Y first (in mm)", severity="warning")
            return None
        try:
            return float(x_input.value), float(y_input.value)
        except ValueError:
            self.app.notify("Invalid X/Y value", severity="error")
            return None

    def _send_command_with_xy(self, cmd: int) -> None:
        xy = self._read_xy_mm()
        if xy is None:
            return
        x_mm, y_mm = xy
        x_ticks = int(x_mm * PUNCHPRESS_ENCODER_TICKS_PER_MM)
        y_ticks = int(y_mm * PUNCHPRESS_ENCODER_TICKS_PER_MM)
        self._send_command(cmd, x_ticks, y_ticks)

    def _send_command(self, cmd: int, x_ticks: int, y_ticks: int) -> None:
        x = max(0, min(0xFFFF, x_ticks))
        y = max(0, min(0xFFFF, y_ticks))
        data = bytes([cmd & 0xFF, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF])
        self.post_message(SendFrame(arb_id=PUNCHPRESS_COMMAND_CAN_ID, data=data))

    def _send_sim_restart(self) -> None:
        x_input = self.query_one("#pp-x", Input)
        y_input = self.query_one("#pp-y", Input)
        try:
            x_rel = float(x_input.value) if x_input.value.strip() else None
            y_rel = float(y_input.value) if y_input.value.strip() else None
        except ValueError:
            self.app.notify("Invalid X/Y value", severity="error")
            return
        # Inputs are safe-zone-relative (matching the displayed coordinates);
        # the SIM_RESTART packet expects absolute mm so add the border zone.
        x_mm = (x_rel + PUNCHPRESS_BORDER_ZONE_MM) if x_rel is not None else None
        y_mm = (y_rel + PUNCHPRESS_BORDER_ZONE_MM) if y_rel is not None else None
        self.post_message(RestartPunchpress(x_mm=x_mm, y_mm=y_mm))
        self.clear_punches()

    # ── auto-run sequence ────────────────────────────────────────────────────

    def _toggle_auto_sequence(self) -> None:
        # Server owns the state machine; just request the desired toggle and
        # wait for the resulting punchpress_auto_run event to update our view.
        self.post_message(SetPunchpressAuto(active=not self._auto_active))
