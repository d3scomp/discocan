"""REST routes for CAN bus operations."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from discocan.device import DeviceManager
from discocan.protocol import CanFramePacket

router = APIRouter(prefix="/api/can", tags=["can"])

_device: DeviceManager | None = None


def init(device: DeviceManager) -> None:
    global _device
    _device = device


def get_device() -> DeviceManager:
    assert _device is not None
    return _device


class SendCanRequest(BaseModel):
    id: int
    data: list[int]


@router.post("/send")
async def send_frame(
    req: SendCanRequest,
    device: DeviceManager = Depends(get_device),
):
    if req.id > 0x7FF:
        raise HTTPException(400, f"Invalid CAN ID: 0x{req.id:X}")
    if len(req.data) > 8:
        raise HTTPException(400, "Data must be ≤ 8 bytes")

    frame = CanFramePacket(arb_id=req.id, dlc=len(req.data), data=bytes(req.data))
    device.send_packet(frame)
    # The firmware echoes a CAN_TX_FRAME on the wire after queueing this on
    # the bus, and that's what becomes the tx trace entry — single source of
    # truth for what actually went on the bus.
    return {"status": "ok"}
