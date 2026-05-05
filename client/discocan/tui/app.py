"""Textual TUI for discocan."""

import asyncio
import warnings
from dataclasses import dataclass

# Textual ≤8.x emits a benign RuntimeWarning about Screen._watch_selections
# never being awaited under some compose patterns. It's harmless — silence it
# so the noise doesn't show up in the user's terminal.
warnings.filterwarnings(
    "ignore",
    message=r".*_watch_selections.*was never awaited.*",
    category=RuntimeWarning,
)

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import ContentSwitcher, Footer, Header

from discocan.config import (
    PUNCHPRESS_BORDER_ZONE_MM,
    PUNCHPRESS_STATUS_CAN_ID,
    PUNCHPRESS_WORK_AREA_HEIGHT_MM,
    PUNCHPRESS_WORK_AREA_WIDTH_MM,
    THERMO_RESET_ID,
)
from discocan.device import DeviceManager
from discocan.event_bus import EventBus
from discocan.protocol import CanFramePacket, SimulationRestartPacket
from discocan.punchpress_auto import PunchpressAutoRun
from discocan.store import Store
from discocan.thermo import encode_thermo_text

from .layouts.can_trace import CANTraceLayout
from .layouts.punchpress import PunchpressLayout
from .layouts.thermometer import ThermometerLayout
from .layouts.trace_panel import TracePanel
from .messages import (
    ResetThermo,
    RestartPunchpress,
    SendFrame,
    SendThermoText,
    SetPunchpressAuto,
)


class DiscocanApp(App):
    """Main Textual application for discocan."""

    TITLE = "discocan v0.1.0"
    SUB_TITLE = "CAN bus monitor"

    CSS = """
    ContentSwitcher {
        height: 1fr;
    }
    CANTraceLayout, ThermometerLayout, PunchpressLayout {
        height: 100%;
    }
"""

    BINDINGS = [
        Binding("f5", "show_layout('can_trace')", "CAN Trace", show=True),
        Binding("f6", "show_layout('thermo')", "Thermometer", show=True),
        Binding("f7", "show_layout('punchpress')", "Punchpress", show=True),
        Binding("ctrl+a", "toggle_autoscroll", "Autoscroll", show=True),
        Binding("ctrl+s", "toggle_pause", "Start/Stop", show=True),
        Binding("ctrl+t", "toggle_hide_tx", "Hide TX", show=True),
        Binding("ctrl+u", "toggle_hide_pp_status", "Hide 0x200", show=True),
        Binding("question_mark", "show_hotkeys", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        # Default Textual ctrl+c is overridden by our custom BINDINGS list, so
        # add it back explicitly with priority — otherwise the user can't bail
        # out of a running TUI from the keyboard except via the 'q' binding.
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
    ]

    # ── Internal message for bus events ──────────────────────────────────────

    @dataclass
    class CANEvent(Message):
        payload: dict

    # ── Init ─────────────────────────────────────────────────────────────────

    def __init__(
        self,
        device: DeviceManager,
        store: Store,
        bus: EventBus,
        auto_run: PunchpressAutoRun,
    ):
        super().__init__()
        self._device = device
        self._store = store
        self._bus = bus
        self._auto_run = auto_run
        self._bus_task: asyncio.Task | None = None
        self._hide_pp_status = False
        self._hide_tx = False
        self._traces_paused = False
        self._traces_autoscroll = True

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with ContentSwitcher(initial="can_trace"):
            yield CANTraceLayout(id="can_trace")
            yield ThermometerLayout(id="thermo")
            yield PunchpressLayout(id="punchpress")
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._bus_task = asyncio.create_task(self._poll_bus())

    async def on_unmount(self) -> None:
        if self._bus_task:
            self._bus_task.cancel()

    async def _poll_bus(self) -> None:
        q = await self._bus.subscribe()
        try:
            while True:
                event = await q.get()
                self.post_message(self.CANEvent(payload=event))
        except asyncio.CancelledError:
            self._bus.unsubscribe(q)

    # ── Bus event → layouts ───────────────────────────────────────────────────

    def on_discocan_app_canevent(self, message: "DiscocanApp.CANEvent") -> None:
        payload = message.payload
        evt_type = payload.get("type")

        if evt_type == "connection_state":
            state = payload["state"]
            labels = {
                "connected": "connected",
                "disconnected": "disconnected — waiting",
                "reconnecting": "reconnecting…",
            }
            self.sub_title = labels.get(state, state)
            return

        if evt_type == "can_frame":
            arb_id = payload["id"]
            if self._hide_pp_status and arb_id == PUNCHPRESS_STATUS_CAN_ID:
                return
            direction = payload["direction"]
            if self._hide_tx and direction == "tx":
                return
            fw_ts = payload.get("fw_timestamp_ms")
            dlc = payload["dlc"]
            data = payload["data"]
            for layout_id in ("can_trace", "thermo", "punchpress"):
                try:
                    self.query_one(f"#{layout_id}").log_entry(direction, fw_ts, arb_id, dlc, data)
                except Exception:
                    pass

        elif evt_type in ("thermo_current", "thermo_minmax"):
            try:
                self.query_one("#thermo", ThermometerLayout).update_thermo(payload)
            except Exception:
                pass

        elif evt_type == "punchpress_status":
            try:
                self.query_one("#punchpress", PunchpressLayout).update_status(payload)
            except Exception:
                pass

        elif evt_type == "punchpress_punch":
            try:
                self.query_one("#punchpress", PunchpressLayout).add_punch(payload)
            except Exception:
                pass

        elif evt_type == "punchpress_controller_status":
            try:
                self.query_one("#punchpress", PunchpressLayout).update_controller_status(payload)
            except Exception:
                pass

        elif evt_type == "punchpress_auto_run":
            try:
                self.query_one("#punchpress", PunchpressLayout).update_auto_run(payload)
            except Exception:
                pass

    # ── Layout messages → hardware ────────────────────────────────────────────

    def _send_can(self, frame: CanFramePacket) -> bool:
        """Hand the frame to the firmware. The firmware echoes back a
        CAN_TX_FRAME after a successful bus queue; that's what generates the
        tx trace entry, so we deliberately don't record one here."""
        try:
            self._device.send_packet(frame)
            return True
        except RuntimeError:
            self.notify("Device disconnected — frame not sent", severity="warning")
            return False

    def on_send_frame(self, message: SendFrame) -> None:
        try:
            frame = CanFramePacket(arb_id=message.arb_id, dlc=len(message.data), data=message.data)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self._send_can(frame)

    def on_reset_thermo(self, message: ResetThermo) -> None:
        self._send_can(CanFramePacket(arb_id=THERMO_RESET_ID, dlc=0, data=b""))

    def on_send_thermo_text(self, message: SendThermoText) -> None:
        for frame in encode_thermo_text(message.text):
            if not self._send_can(frame):
                return  # device disconnected — bail out, don't keep trying

    def on_set_punchpress_auto(self, message: SetPunchpressAuto) -> None:
        if message.active:
            self._auto_run.start()
        else:
            self._auto_run.stop()

    def on_restart_punchpress(self, message: RestartPunchpress) -> None:
        x_mm = (
            message.x_mm
            if message.x_mm is not None
            else PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_WIDTH_MM / 2
        )
        y_mm = (
            message.y_mm
            if message.y_mm is not None
            else PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_HEIGHT_MM / 2
        )
        try:
            self._device.send_packet(
                SimulationRestartPacket(
                    x_100um=int(x_mm * 100),
                    y_100um=int(y_mm * 100),
                )
            )
        except RuntimeError:
            self.notify("Device disconnected — restart not sent", severity="warning")

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_show_layout(self, layout: str) -> None:
        self.query_one(ContentSwitcher).current = layout

    def action_toggle_hide_pp_status(self) -> None:
        self._hide_pp_status = not self._hide_pp_status
        self.notify(
            f"Punchpress status (0x{PUNCHPRESS_STATUS_CAN_ID:03X}) frames "
            + ("hidden" if self._hide_pp_status else "shown")
        )

    def action_toggle_hide_tx(self) -> None:
        self._hide_tx = not self._hide_tx
        self.notify("TX frames " + ("hidden" if self._hide_tx else "shown"))

    def action_toggle_pause(self) -> None:
        self._traces_paused = not self._traces_paused
        for panel in self.query(TracePanel):
            panel.set_paused(self._traces_paused)
        self.notify(f"Trace {'paused' if self._traces_paused else 'running'}")

    def action_toggle_autoscroll(self) -> None:
        self._traces_autoscroll = not self._traces_autoscroll
        for panel in self.query(TracePanel):
            panel.set_autoscroll(self._traces_autoscroll)
        self.notify(f"Autoscroll {'on' if self._traces_autoscroll else 'off'}")

    def action_show_hotkeys(self) -> None:
        self.notify(
            "F5: CAN Trace\n"
            "F6: Thermometer\n"
            "F7: Punchpress\n"
            "Ctrl+A: toggle autoscroll\n"
            "Ctrl+S: start/stop trace\n"
            "Ctrl+T: toggle hide TX\n"
            "Ctrl+U: toggle hide 0x200 (punchpress status)\n"
            "?: this help\n"
            "q: quit",
            title="Global keys",
            timeout=8,
        )
