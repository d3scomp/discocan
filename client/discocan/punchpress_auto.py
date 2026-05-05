"""Server-side auto-run engine for the punchpress.

Holds the canonical state for the 50-target circular auto-run sequence so
that both the TUI and the web frontend act as thin clients: each just sends
start/stop commands and reflects the current state from `punchpress_auto_run`
bus events. Either UI can start a run and the other can stop it.
"""

import math

from .config import (
    PUNCHPRESS_COMMAND_CAN_ID,
    PUNCHPRESS_COMMAND_HOME,
    PUNCHPRESS_COMMAND_PUNCH_AT,
    PUNCHPRESS_ENCODER_TICKS_PER_MM,
    PUNCHPRESS_WORK_AREA_HEIGHT_MM,
    PUNCHPRESS_WORK_AREA_WIDTH_MM,
)
from .device import DeviceManager
from .event_bus import EventBus
from .protocol import CanFramePacket

NUM_TARGETS = 50
RADIUS_TICKS = 5000  # 500 mm — fits well inside the 1 m × 0.75 m safe zone


def _build_targets() -> list[tuple[int, int]]:
    cx = (PUNCHPRESS_WORK_AREA_WIDTH_MM // 2) * PUNCHPRESS_ENCODER_TICKS_PER_MM
    cy = (PUNCHPRESS_WORK_AREA_HEIGHT_MM // 2) * PUNCHPRESS_ENCODER_TICKS_PER_MM
    return [
        (
            int(cx + RADIUS_TICKS * math.cos(2 * math.pi * i / NUM_TARGETS)),
            int(cy + RADIUS_TICKS * math.sin(2 * math.pi * i / NUM_TARGETS)),
        )
        for i in range(NUM_TARGETS)
    ]


class PunchpressAutoRun:
    """Drives the s32 controller through HOME → 50 PUNCH_AT commands.

    The state machine advances on the falling edge of the controller's busy
    bit (CAN frame 0x203), which the packet handler forwards via
    `on_controller_status`. State changes are published as
    `punchpress_auto_run` events so connected clients can reflect them.
    """

    def __init__(self, device: DeviceManager, bus: EventBus):
        self._device = device
        self._bus = bus
        self._active = False
        self._index = 0
        self._step = "idle"  # "idle" | "home" | "punch"
        self._prev_busy = False
        self._targets = _build_targets()

    @property
    def state(self) -> dict:
        return {
            "active": self._active,
            "index": self._index,
            "total": len(self._targets),
        }

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._index = 0
        self._step = "home"
        # Reset edge-detect state so the first busy→idle transition we see
        # after HOME completes counts as the trigger.
        self._prev_busy = False
        self._publish()
        self._send_command(PUNCHPRESS_COMMAND_HOME, 0, 0)

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._step = "idle"
        self._publish()

    def on_controller_status(self, busy: bool) -> None:
        if self._active and self._prev_busy and not busy:
            if self._step == "home":
                self._index = 0
                self._step = "punch"
                self._publish()
                self._send_next_punch()
            elif self._step == "punch":
                self._index += 1
                if self._index >= len(self._targets):
                    self._active = False
                    self._step = "idle"
                    self._publish()
                else:
                    self._publish()
                    self._send_next_punch()
        self._prev_busy = busy

    def _send_next_punch(self) -> None:
        x, y = self._targets[self._index]
        self._send_command(PUNCHPRESS_COMMAND_PUNCH_AT, x, y)

    def _send_command(self, cmd: int, x_ticks: int, y_ticks: int) -> None:
        x = max(0, min(0xFFFF, x_ticks))
        y = max(0, min(0xFFFF, y_ticks))
        data = bytes([cmd & 0xFF, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF])
        try:
            self._device.send_packet(
                CanFramePacket(arb_id=PUNCHPRESS_COMMAND_CAN_ID, dlc=5, data=data)
            )
        except RuntimeError:
            # Device disconnected mid-sequence — abort.
            self._active = False
            self._step = "idle"
            self._publish()

    def _publish(self) -> None:
        self._bus.publish_sync({"type": "punchpress_auto_run", **self.state})
