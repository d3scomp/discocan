"""Layout 1: CAN trace (left) + sidebar with controls and send form (right)."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Button, Input, Rule, Static

from discocan.config import get_key_frames
from discocan.tui.messages import SendFrame

from .trace_panel import TracePanel


def _build_frames_text() -> str:
    lines = []
    for key, frame in get_key_frames().items():
        hex_data = " ".join(f"{b:02X}" for b in frame.data) if frame.data else "(empty)"
        lines.append(f"[b]{key}[/b]  0x{frame.arb_id:03X}  {hex_data}")
    return "\n".join(lines)


class CANTraceLayout(Horizontal):
    DEFAULT_CSS = """
    CANTraceLayout > TracePanel {
        width: 1fr;
    }
    CANTraceLayout > #can-sidebar {
        width: 50;
        min-width: 25;
        height: 100%;
        padding: 1;
        border-left: tall $panel-darken-2;
    }
    CANTraceLayout > #can-sidebar Button {
        width: 100%;
        margin-bottom: 1;
    }
    CANTraceLayout > #can-sidebar Input {
        width: 100%;
        margin-bottom: 1;
    }
    CANTraceLayout > #can-sidebar .sidebar-label {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TracePanel(
            startup_msg="[dim]-- discocan CAN trace ready --[/dim]",
        )
        with Vertical(id="can-sidebar"):
            yield Static("[b]Predefined frames[/b]", classes="sidebar-label", markup=True)
            yield Static(_build_frames_text(), classes="sidebar-label", markup=True)
            yield Rule()
            yield Static("[b]Send custom frame[/b]", classes="sidebar-label", markup=True)
            yield Input(placeholder="CAN ID (hex)", id="can-input-id")
            yield Input(placeholder="Data (hex bytes)", id="can-input-data")
            yield Button("Send", id="can-btn-send", variant="primary")

    def log_entry(self, direction: str, fw_timestamp_ms: int | None, arb_id: int, dlc: int, data: list[int]) -> None:
        self.query_one(TracePanel).log_entry(direction, fw_timestamp_ms, arb_id, dlc, data)

    def on_key(self, event: Key) -> None:
        if event.key in get_key_frames():
            frame = get_key_frames()[event.key]
            self.post_message(SendFrame(arb_id=frame.arb_id, data=frame.data))
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "can-btn-send":
            self._send_from_inputs()

    def _send_from_inputs(self) -> None:
        id_input = self.query_one("#can-input-id", Input)
        data_input = self.query_one("#can-input-data", Input)
        try:
            arb_id = int(id_input.value.strip(), 16)
        except ValueError:
            self.app.notify("Invalid CAN ID", severity="error")
            return
        try:
            data = bytes(int(x, 16) for x in data_input.value.split()) if data_input.value.strip() else b""
        except ValueError:
            self.app.notify("Invalid data bytes", severity="error")
            return
        self.post_message(SendFrame(arb_id=arb_id, data=data))
        id_input.value = ""
        data_input.value = ""
