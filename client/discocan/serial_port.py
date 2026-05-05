"""Serial port communication for DISCOCAN protocol."""

import struct
import threading
from typing import Callable, Optional

import serial

from .protocol import HEADER, Packet, crc32_mpeg2, decode_packet

RECONNECT_DELAY = 2.0  # seconds between reconnect attempts


class SerialPort:
    """Serial port manager with packet protocol support."""

    def __init__(self, port: str, baudrate: int = 1000000):
        self.port = serial.Serial(port, baudrate, timeout=0.1)
        self._stop_event = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self.on_packet_received: Optional[Callable[[Packet], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None

    def send_packet(self, packet: Packet) -> None:
        data = packet.encode()
        self.port.write(data)

    def start_receiver(self) -> None:
        if self._rx_thread is not None and self._rx_thread.is_alive():
            return
        self._stop_event.clear()
        self._rx_thread = threading.Thread(target=self._receiver_loop, daemon=True)
        self._rx_thread.start()

    def stop_receiver(self) -> None:
        self._stop_event.set()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)

    def close(self) -> None:
        self.stop_receiver()
        try:
            self.port.close()
        except Exception:
            pass

    def _receiver_loop(self) -> None:
        STATE_SYNC_0 = 0
        STATE_SYNC_1 = 1
        STATE_TYPE = 2
        STATE_PAYLOAD = 3

        sync_state = STATE_SYNC_0
        packet_type = 0
        payload_size = 0
        buf = bytearray()

        while not self._stop_event.is_set():
            try:
                raw = self.port.read(self.port.in_waiting or 1)
            except serial.SerialException:
                # Port lost — signal caller and exit thread
                if self.on_disconnect is not None:
                    self.on_disconnect()
                return

            if not raw:
                continue

            for byte in raw:
                if sync_state == STATE_SYNC_0:
                    if byte == HEADER[0]:
                        sync_state = STATE_SYNC_1

                elif sync_state == STATE_SYNC_1:
                    if byte == HEADER[1]:
                        sync_state = STATE_TYPE
                    elif byte == HEADER[0]:
                        sync_state = STATE_SYNC_1
                    else:
                        sync_state = STATE_SYNC_0

                elif sync_state == STATE_TYPE:
                    packet_type = byte
                    payload_size = self._get_payload_size(packet_type)
                    if payload_size is not None:
                        sync_state = STATE_PAYLOAD
                        buf.clear()
                    else:
                        sync_state = STATE_SYNC_0

                elif sync_state == STATE_PAYLOAD:
                    buf.append(byte)
                    if len(buf) == payload_size + 4:  # payload + CRC32
                        sync_state = STATE_SYNC_0
                        self._process_packet(packet_type, bytes(buf))

    def _get_payload_size(self, packet_type: int) -> Optional[int]:
        from .protocol import PACKET_TYPES
        packet_class = PACKET_TYPES.get(packet_type)
        if packet_class is None:
            return None
        return getattr(packet_class, "payload_size", None)

    def _process_packet(self, packet_type: int, data: bytes) -> None:
        payload_size = len(data) - 4
        payload = data[:payload_size]
        rx_crc = struct.unpack_from("<I", data, payload_size)[0]

        padded_payload = payload + b"\x00" * ((4 - len(payload) % 4) % 4)
        crc_data = struct.pack("<I", packet_type) + padded_payload
        calc_crc = crc32_mpeg2(crc_data)

        if rx_crc != calc_crc:
            print(f"[CRC ERROR] Type=0x{packet_type:02X}, Expected 0x{calc_crc:08X}, got 0x{rx_crc:08X}")
            return

        try:
            packet = decode_packet(packet_type, payload)
            if self.on_packet_received is not None:
                self.on_packet_received(packet)
        except ValueError as e:
            print(f"[DECODE ERROR] {e}")
