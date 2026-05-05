"""Layout 2: trace panel (left) + thermometer data + text send (right)."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.widgets import Button, Static, TextArea

from discocan.tui.messages import ResetThermo, SendThermoText

from .trace_panel import TracePanel


class ThermometerLayout(Horizontal):
    DEFAULT_CSS = """
    ThermometerLayout > TracePanel {
        width: 1fr;
    }
    ThermometerLayout > #thermo-panel {
        width: 50;
        min-width: 25;
        height: 100%;
        padding: 1;
        border-left: tall $panel-darken-2;
    }
    #thermo-stats {
        height: auto;
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
    }
    #thermo-text-input {
        height: 1fr;
        border: solid $secondary;
    }
    #thermo-buttons {
        height: auto;
        padding-top: 1;
    }
    #thermo-buttons Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TracePanel()
        with Vertical(id="thermo-panel"):
            yield Static(self._stats_text(), id="thermo-stats")
            yield TextArea(id="thermo-text-input")
            with Horizontal(id="thermo-buttons"):
                yield Button("Send Text", id="btn-send-text", variant="primary")
                yield Button("Reset [r]", id="btn-reset", variant="warning")

    def _stats_text(self) -> str:
        t = getattr(self, "_thermo", None)
        if t is None:
            return "[b]Thermometer[/b]\n\nNo data yet"

        temp = f'{t["temp"]:3.3f} C' if 'temp' in t else '?'
        hum = f'{t["humidity"]:3.3f} %' if 'humidity' in t else '?'
        min_temp = f'{t["min_temp"]:3.3f} C' if 'min_temp' in t else '?'
        max_temp = f'{t["max_temp"]:3.3f} C' if 'max_temp' in t else '?'
        min_hum = f'{t["min_hum"]:3.3f} %' if 'min_hum' in t else '?'
        max_hum = f'{t["max_hum"]:3.3f} %' if 'max_hum' in t else '?'

        return (
            f"[b]Thermometer[/b]\n\n"
            f"Temperature: {temp}\n"
            f"Humidity:    {hum}\n\n"
            f"Min Temp.:   {min_temp}\n"
            f"Max Temp.:   {max_temp}\n"
            f"Min Hum.:    {min_hum}\n"
            f"Max Hum.:    {max_hum}"
        )

    def update_thermo(self, data: dict) -> None:
        if not hasattr(self, "_thermo"):
            self._thermo = {}
        self._thermo.update(data)
        try:
            self.query_one("#thermo-stats", Static).update(self._stats_text())
        except Exception:
            pass

    def log_entry(self, direction: str, fw_timestamp_ms: int | None, arb_id: int, dlc: int, data: list[int]) -> None:
        self.query_one(TracePanel).log_entry(direction, fw_timestamp_ms, arb_id, dlc, data)

    def on_key(self, event: Key) -> None:
        if event.key == "r":
            self.post_message(ResetThermo())
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-reset":
            self.post_message(ResetThermo())
        elif event.button.id == "btn-send-text":
            ta = self.query_one("#thermo-text-input", TextArea)
            text = ta.text
            if text.strip():
                self.post_message(SendThermoText(text=text))
                ta.clear()
