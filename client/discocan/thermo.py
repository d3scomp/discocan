"""Temperature/humidity decoding and text-to-CAN chunking."""

from .config import THERMO_TEXT_ID
from .protocol import CanFramePacket


def decode_temp(raw: int) -> float:
    return -45 + (175 / 3) * raw / 21845


def decode_hum(raw: int) -> float:
    return -6 + (125 / 3) * raw / 21845


def encode_thermo_text(text: str) -> list[CanFramePacket]:
    """Chunk text into 0x103 CAN frames. Bit 7 of each byte set if char follows a newline."""
    bytes_out = []
    next_is_newline = True
    for ch in text:
        if ch == "\n":
            next_is_newline = True
        else:
            b = ord(ch) & 0x7F
            if next_is_newline:
                b |= 0x80
            bytes_out.append(b)
            next_is_newline = False

    frames = []
    for i in range(0, max(1, len(bytes_out)), 8):
        chunk = bytes(bytes_out[i : i + 8])
        frames.append(CanFramePacket(arb_id=THERMO_TEXT_ID, dlc=len(chunk), data=chunk))
    return frames
