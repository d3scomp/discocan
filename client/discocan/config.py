"""Configuration constants for discocan."""

MAX_PUNCHES = 1000
DEFAULT_WEB_PORT = 8765
BAUD_RATE = 1_000_000
DEVICE_VID = 0x0483  # STMicroelectronics
DEVICE_PID = 0x5740  # STM32 CDC Virtual COM Port

# Thermometer CAN IDs
THERMO_CURRENT_ID = 0x100
THERMO_MINMAX_ID = 0x101
THERMO_RESET_ID = 0x102
THERMO_TEXT_ID = 0x103

# Punchpress geometry (matches firmware constants)
PUNCHPRESS_WORK_AREA_WIDTH_MM = 2000
PUNCHPRESS_WORK_AREA_HEIGHT_MM = 1500
PUNCHPRESS_BORDER_ZONE_MM = 100

# Punchpress CAN IDs (firmware sends status on the bus, expects punch requests)
PUNCHPRESS_STATUS_CAN_ID = 0x200
PUNCHPRESS_COMMAND_CAN_ID = 0x202
PUNCHPRESS_CONTROLLER_STATUS_CAN_ID = 0x203

# Punchpress command opcodes (byte 0 of 0x202 frame)
PUNCHPRESS_COMMAND_HOME = 0x00
PUNCHPRESS_COMMAND_MOVE_TO = 0x01
PUNCHPRESS_COMMAND_PUNCH_AT = 0x02

# Punchpress controller status bits (byte 0 of 0x203 frame)
PUNCHPRESS_CTRL_STATUS_BUSY_BIT = 1 << 0

# Encoder ticks per mm (matches firmware sim ENCODER_TICKS_PER_MM, and
# the s32 controller after homing uses the same units).
PUNCHPRESS_ENCODER_TICKS_PER_MM = 10

# Punchpress status bits (must match firmware bit positions)
PUNCHPRESS_STATUS_TOP_BORDER = 1 << 0
PUNCHPRESS_STATUS_BOTTOM_BORDER = 1 << 1
PUNCHPRESS_STATUS_LEFT_BORDER = 1 << 2
PUNCHPRESS_STATUS_RIGHT_BORDER = 1 << 3
PUNCHPRESS_STATUS_HEAD_UP = 1 << 4
PUNCHPRESS_STATUS_FAIL = 1 << 5

# Predefined hotkey → CAN frame (lazy-initialized to avoid circular import)
def _make_key_frames():
    from discocan.protocol import CanFramePacket
    return {
        "1": CanFramePacket(0x100, 2, b"\x01\x00"),
        "2": CanFramePacket(0x200, 4, b"\xDE\xAD\xBE\xEF"),
        "3": CanFramePacket(0x300, 8, b"\x01\x02\x03\x04\x05\x06\x07\x08"),
        "4": CanFramePacket(0x400, 0, b""),
        "5": CanFramePacket(0x500, 1, b"\xFF"),
    }


KEY_FRAMES = None  # Populated on first access via get_key_frames()


def get_key_frames() -> dict:
    global KEY_FRAMES
    if KEY_FRAMES is None:
        KEY_FRAMES = _make_key_frames()
    return KEY_FRAMES
