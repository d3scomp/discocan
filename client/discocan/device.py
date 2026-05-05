"""DeviceManager: singleton managing the DISCOCAN serial device."""

import asyncio
from typing import Callable, Optional

import serial
import serial.tools.list_ports

from .config import BAUD_RATE, DEVICE_PID, DEVICE_VID
from .protocol import Packet
from .serial_port import SerialPort

RECONNECT_DELAY = 2.0  # seconds between attempts


class DeviceNotFoundError(Exception):
    pass


class PortInUseError(Exception):
    """Serial port is locked by another process — likely a second discocan server."""
    pass


def _is_port_locked_error(exc: serial.SerialException) -> bool:
    """Heuristic: detect 'port already in use' across pyserial messages."""
    msg = str(exc).lower()
    return any(
        marker in msg
        for marker in ("permissionerror", "access is denied", "already in use", "could not open port")
    )


class DeviceManager:
    def __init__(self, port: Optional[str] = None):
        # None means auto-detect; we re-detect on every reconnect attempt.
        self._fixed_port = port
        self._serial: Optional[SerialPort] = None
        self._on_packet: Optional[Callable[[Packet], None]] = None
        self._on_state: Optional[Callable[[str], None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._disconnect_event: Optional[asyncio.Event] = None
        self._has_ever_connected = False
        self._current_state: str = "unknown"

        # Validate early so the error surfaces before asyncio.run()
        if port is None:
            self._auto_detect()  # raises DeviceNotFoundError if nothing found right now

    # ── Port detection ────────────────────────────────────────────────────────

    def _auto_detect(self) -> str:
        for info in serial.tools.list_ports.comports():
            if info.vid == DEVICE_VID and info.pid == DEVICE_PID:
                return info.device
        raise DeviceNotFoundError(
            f"No device with VID:PID={DEVICE_VID:04X}:{DEVICE_PID:04X} found. "
            "Connect the DISCOCAN adapter and try again, or run "
            "'discocan list-ports' to see all available ports."
        )

    def _resolve_port(self) -> str:
        return self._fixed_port if self._fixed_port is not None else self._auto_detect()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_handler(self, callback: Callable[[Packet], None]) -> None:
        self._on_packet = callback

    def set_state_handler(self, callback: Callable[[str], None]) -> None:
        """Callback receives one of: 'connected', 'disconnected', 'reconnecting'."""
        self._on_state = callback

    def send_packet(self, packet: Packet) -> None:
        if self._serial is None:
            raise RuntimeError("Device not connected")
        self._serial.send_packet(packet)

    # ── Async run loop ────────────────────────────────────────────────────────

    async def run(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._disconnect_event = asyncio.Event()
        try:
            while True:
                try:
                    await self._connect_and_run()
                    self._has_ever_connected = True
                except serial.SerialException as e:
                    if not self._has_ever_connected and _is_port_locked_error(e):
                        # First-attempt failure with the OS reporting the port as
                        # already in use — almost always means another discocan
                        # server is running. Bail out fast with a clear message.
                        raise PortInUseError(
                            f"Cannot open serial port: {e}\n"
                            "Another discocan server is likely already running. "
                            "Stop it first."
                        ) from e
                    print(f"[device] {e}")
                    self._publish_state("reconnecting")
                    await asyncio.sleep(RECONNECT_DELAY)
                except DeviceNotFoundError as e:
                    print(f"[device] {e}")
                    self._publish_state("reconnecting")
                    await asyncio.sleep(RECONNECT_DELAY)
                except asyncio.CancelledError:
                    return
        finally:
            if self._serial is not None:
                self._serial.close()
                self._serial = None

    async def _connect_and_run(self) -> None:
        port = self._resolve_port()
        try:
            self._serial = SerialPort(port, BAUD_RATE)
        except serial.SerialException as e:
            raise serial.SerialException(str(e))

        def _bridge(packet: Packet) -> None:
            if self._on_packet is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(self._on_packet, packet)

        def _on_disconnect() -> None:
            if self._loop is not None and self._disconnect_event is not None:
                self._loop.call_soon_threadsafe(self._disconnect_event.set)

        self._serial.on_packet_received = _bridge
        self._serial.on_disconnect = _on_disconnect
        self._serial.start_receiver()
        self._publish_state("connected")

        # Block until the serial thread signals a disconnect
        await self._disconnect_event.wait()
        self._disconnect_event.clear()

        self._serial.close()
        self._serial = None
        self._publish_state("disconnected")

    def _publish_state(self, state: str) -> None:
        self._current_state = state
        if self._on_state is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._on_state, state)

    @property
    def current_state(self) -> str:
        """Last connection state — for snapshotting to late WS subscribers."""
        return self._current_state
