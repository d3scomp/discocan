"""Shared TUI message types."""

from dataclasses import dataclass

from textual.message import Message


@dataclass
class SendFrame(Message):
    arb_id: int
    data: bytes


class ResetThermo(Message):
    pass


@dataclass
class SendThermoText(Message):
    text: str


@dataclass
class RestartPunchpress(Message):
    x_mm: float | None
    y_mm: float | None


@dataclass
class SetPunchpressAuto(Message):
    """Toggle the server-side punchpress auto-run sequence on/off."""
    active: bool
