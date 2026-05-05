"""In-memory state: thermometer state, punchpress state."""

from collections import deque
from dataclasses import dataclass

from .config import (
    MAX_PUNCHES,
    PUNCHPRESS_STATUS_BOTTOM_BORDER,
    PUNCHPRESS_STATUS_FAIL,
    PUNCHPRESS_STATUS_HEAD_UP,
    PUNCHPRESS_STATUS_LEFT_BORDER,
    PUNCHPRESS_STATUS_RIGHT_BORDER,
    PUNCHPRESS_STATUS_TOP_BORDER,
)


@dataclass
class ThermoState:
    current_temp: float | None = None
    current_hum: float | None = None
    min_temp: float | None = None
    min_hum: float | None = None
    max_temp: float | None = None
    max_hum: float | None = None


@dataclass
class PunchpressState:
    x_mm: float = 0.0
    y_mm: float = 0.0
    head_up: bool = True
    fail: bool = False
    border_top: bool = False
    border_bottom: bool = False
    border_left: bool = False
    border_right: bool = False
    last_update: float | None = None


@dataclass
class PunchEntry:
    timestamp: float
    x_mm: float
    y_mm: float


class Store:
    def __init__(self):
        self.thermo = ThermoState()
        self.punchpress = PunchpressState()
        self.punches: deque[PunchEntry] = deque(maxlen=MAX_PUNCHES)

    def update_thermo_current(self, raw_temp: int, raw_hum: int) -> None:
        from .thermo import decode_temp, decode_hum
        self.thermo.current_temp = decode_temp(raw_temp)
        self.thermo.current_hum = decode_hum(raw_hum)

    def update_thermo_minmax(
        self,
        raw_min_temp: int,
        raw_min_hum: int,
        raw_max_temp: int,
        raw_max_hum: int,
    ) -> None:
        from .thermo import decode_temp, decode_hum
        self.thermo.min_temp = decode_temp(raw_min_temp)
        self.thermo.min_hum = decode_hum(raw_min_hum)
        self.thermo.max_temp = decode_temp(raw_max_temp)
        self.thermo.max_hum = decode_hum(raw_max_hum)

    def update_punchpress_status(
        self, x_100um: int, y_100um: int, status_bits: int, timestamp: float
    ) -> None:
        pp = self.punchpress
        pp.x_mm = x_100um / 100.0
        pp.y_mm = y_100um / 100.0
        pp.border_top = bool(status_bits & PUNCHPRESS_STATUS_TOP_BORDER)
        pp.border_bottom = bool(status_bits & PUNCHPRESS_STATUS_BOTTOM_BORDER)
        pp.border_left = bool(status_bits & PUNCHPRESS_STATUS_LEFT_BORDER)
        pp.border_right = bool(status_bits & PUNCHPRESS_STATUS_RIGHT_BORDER)
        pp.head_up = bool(status_bits & PUNCHPRESS_STATUS_HEAD_UP)
        pp.fail = bool(status_bits & PUNCHPRESS_STATUS_FAIL)
        pp.last_update = timestamp

    def add_punch(self, x_100um: int, y_100um: int, timestamp: float) -> None:
        self.punches.append(
            PunchEntry(timestamp=timestamp, x_mm=x_100um / 100.0, y_mm=y_100um / 100.0)
        )

    def clear_punches(self) -> None:
        self.punches.clear()
