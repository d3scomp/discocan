"""Protocol definitions and packet classes for DISCOCAN serial communication."""

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import crcmod

# Protocol constants
HEADER = bytes([0xAA, 0x55])
PACKET_TYPE_CAN_FRAME = 0x01           # CAN frame received from the bus (rx)
PACKET_TYPE_SIMULATION_RESTART = 0x02
PACKET_TYPE_SIMULATION_STATUS = 0x03
PACKET_TYPE_SIMULATION_PUNCH = 0x04
PACKET_TYPE_CAN_TX_FRAME = 0x05        # CAN frame the firmware put on the bus

# CRC-32/MPEG-2: poly 0x04C11DB7, init 0xFFFFFFFF, no reflection, no final XOR
crc32_mpeg2 = crcmod.mkCrcFun(0x104C11DB7, initCrc=0xFFFFFFFF, rev=False, xorOut=0)


class Packet(ABC):
    """Base class for all packet types."""

    packet_type: ClassVar[int]

    @abstractmethod
    def encode_payload(self) -> bytes:
        """Encode packet payload (without header, type, or CRC)."""
        pass

    @classmethod
    @abstractmethod
    def decode_payload(cls, payload: bytes) -> "Packet":
        """Decode packet from payload bytes."""
        pass

    def encode(self) -> bytes:
        """Encode complete packet with header, type, payload, and CRC."""
        payload = self.encode_payload()

        # CRC is computed over: packet_type (as uint32_t LE) + payload (zero-padded
        # to a multiple of 4 bytes). Mirrors STM32 hardware CRC fed 32-bit words
        # via __REV with the type written first as the seed of the calculation.
        padded_payload = payload + b"\x00" * ((4 - len(payload) % 4) % 4)
        crc_data = struct.pack("<I", self.packet_type) + padded_payload
        crc = crc32_mpeg2(crc_data)

        return HEADER + bytes([self.packet_type]) + payload + struct.pack("<I", crc)


@dataclass
class CanFramePacket(Packet):
    """CAN frame packet (type 0x01).

    timestamp_ms is set by the firmware (HAL_GetTick()) on its way to the host;
    when the host builds a CAN_FRAME packet to send to the firmware it can
    leave it 0 — the firmware overwrites it on the way back.
    """

    packet_type: ClassVar[int] = PACKET_TYPE_CAN_FRAME
    payload_size: ClassVar[int] = 17  # 4 (timestamp_ms) + 4 (arb_id) + 1 (dlc) + 8 (data)

    arb_id: int           # 11-bit CAN ID
    dlc: int              # Data length code (0-8)
    data: bytes           # Up to 8 bytes of data
    timestamp_ms: int = 0  # firmware HAL_GetTick() at send time (boot-relative)

    def __post_init__(self):
        """Validate CAN frame parameters."""
        if self.arb_id > 0x7FF:
            raise ValueError(f"Invalid CAN ID: 0x{self.arb_id:X} (max 0x7FF)")
        if self.dlc > 8:
            raise ValueError(f"Invalid DLC: {self.dlc} (max 8)")
        if len(self.data) > 8:
            raise ValueError(f"Invalid data length: {len(self.data)} (max 8)")

    def encode_payload(self) -> bytes:
        """Encode CAN frame as 17-byte payload."""
        return (
            struct.pack("<IIB", self.timestamp_ms & 0xFFFFFFFF, self.arb_id, self.dlc)
            + self.data.ljust(8, b"\x00")[:8]
        )

    @classmethod
    def decode_payload(cls, payload: bytes) -> "CanFramePacket":
        """Decode 17-byte payload into CAN frame packet."""
        if len(payload) != cls.payload_size:
            raise ValueError(f"Invalid payload size: {len(payload)} (expected {cls.payload_size})")

        timestamp_ms, arb_id, dlc = struct.unpack_from("<IIB", payload, 0)
        data = payload[9 : 9 + dlc]

        return cls(arb_id=arb_id, dlc=dlc, data=data, timestamp_ms=timestamp_ms)

    def __str__(self) -> str:
        """Format CAN frame for display."""
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return f"ID=0x{self.arb_id:03X} DLC={self.dlc} [{hex_data}]"


@dataclass
class CanTxFramePacket(Packet):
    """CAN frame the firmware itself put on the bus (type 0x05).

    Same payload layout as CanFramePacket — separate class so dispatchers can
    label it as a tx entry in the trace, distinguishing it from rx frames the
    firmware received from the bus.
    """

    packet_type: ClassVar[int] = PACKET_TYPE_CAN_TX_FRAME
    payload_size: ClassVar[int] = 17

    arb_id: int
    dlc: int
    data: bytes
    timestamp_ms: int = 0

    def __post_init__(self):
        if self.arb_id > 0x7FF:
            raise ValueError(f"Invalid CAN ID: 0x{self.arb_id:X} (max 0x7FF)")
        if self.dlc > 8:
            raise ValueError(f"Invalid DLC: {self.dlc} (max 8)")
        if len(self.data) > 8:
            raise ValueError(f"Invalid data length: {len(self.data)} (max 8)")

    def encode_payload(self) -> bytes:
        return (
            struct.pack("<IIB", self.timestamp_ms & 0xFFFFFFFF, self.arb_id, self.dlc)
            + self.data.ljust(8, b"\x00")[:8]
        )

    @classmethod
    def decode_payload(cls, payload: bytes) -> "CanTxFramePacket":
        if len(payload) != cls.payload_size:
            raise ValueError(f"Invalid payload size: {len(payload)} (expected {cls.payload_size})")
        timestamp_ms, arb_id, dlc = struct.unpack_from("<IIB", payload, 0)
        data = payload[9 : 9 + dlc]
        return cls(arb_id=arb_id, dlc=dlc, data=data, timestamp_ms=timestamp_ms)

    def __str__(self) -> str:
        hex_data = " ".join(f"{b:02X}" for b in self.data)
        return f"ID=0x{self.arb_id:03X} DLC={self.dlc} [{hex_data}]"


@dataclass
class SimulationRestartPacket(Packet):
    """Punchpress simulation restart command (type 0x02)."""

    packet_type: ClassVar[int] = PACKET_TYPE_SIMULATION_RESTART
    payload_size: ClassVar[int] = 8  # 4 (x_100um) + 4 (y_100um)

    x_100um: int  # signed int32, position in 0.1 mm units
    y_100um: int

    def encode_payload(self) -> bytes:
        return struct.pack("<ii", self.x_100um, self.y_100um)

    @classmethod
    def decode_payload(cls, payload: bytes) -> "SimulationRestartPacket":
        if len(payload) != cls.payload_size:
            raise ValueError(f"Invalid payload size: {len(payload)} (expected {cls.payload_size})")
        x, y = struct.unpack("<ii", payload)
        return cls(x_100um=x, y_100um=y)


@dataclass
class SimulationStatusPacket(Packet):
    """Punchpress simulation status (type 0x03), sent every 100 ms."""

    packet_type: ClassVar[int] = PACKET_TYPE_SIMULATION_STATUS
    payload_size: ClassVar[int] = 9  # 4 (x_100um) + 4 (y_100um) + 1 (status_bits)

    x_100um: int
    y_100um: int
    status_bits: int

    def encode_payload(self) -> bytes:
        return struct.pack("<iiB", self.x_100um, self.y_100um, self.status_bits)

    @classmethod
    def decode_payload(cls, payload: bytes) -> "SimulationStatusPacket":
        if len(payload) != cls.payload_size:
            raise ValueError(f"Invalid payload size: {len(payload)} (expected {cls.payload_size})")
        x, y, bits = struct.unpack("<iiB", payload)
        return cls(x_100um=x, y_100um=y, status_bits=bits)


@dataclass
class SimulationPunchPacket(Packet):
    """Punchpress punch event (type 0x04), sent on each punch."""

    packet_type: ClassVar[int] = PACKET_TYPE_SIMULATION_PUNCH
    payload_size: ClassVar[int] = 8

    x_100um: int
    y_100um: int

    def encode_payload(self) -> bytes:
        return struct.pack("<ii", self.x_100um, self.y_100um)

    @classmethod
    def decode_payload(cls, payload: bytes) -> "SimulationPunchPacket":
        if len(payload) != cls.payload_size:
            raise ValueError(f"Invalid payload size: {len(payload)} (expected {cls.payload_size})")
        x, y = struct.unpack("<ii", payload)
        return cls(x_100um=x, y_100um=y)


# Packet type registry
PACKET_TYPES = {
    PACKET_TYPE_CAN_FRAME: CanFramePacket,
    PACKET_TYPE_SIMULATION_RESTART: SimulationRestartPacket,
    PACKET_TYPE_SIMULATION_STATUS: SimulationStatusPacket,
    PACKET_TYPE_SIMULATION_PUNCH: SimulationPunchPacket,
    PACKET_TYPE_CAN_TX_FRAME: CanTxFramePacket,
}


def decode_packet(packet_type: int, payload: bytes) -> Packet:
    """Decode a packet from type and payload."""
    packet_class = PACKET_TYPES.get(packet_type)
    if packet_class is None:
        raise ValueError(f"Unknown packet type: 0x{packet_type:02X}")
    return packet_class.decode_payload(payload)
