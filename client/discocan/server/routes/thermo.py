"""REST routes for thermometer operations."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from discocan.config import THERMO_RESET_ID
from discocan.device import DeviceManager
from discocan.protocol import CanFramePacket
from discocan.store import Store
from discocan.thermo import encode_thermo_text

router = APIRouter(prefix="/api/thermo", tags=["thermo"])

_device: DeviceManager | None = None
_store: Store | None = None


def init(device: DeviceManager, store: Store) -> None:
    global _device, _store
    _device = device
    _store = store


def get_device() -> DeviceManager:
    assert _device is not None
    return _device


def get_store() -> Store:
    assert _store is not None
    return _store


class TextRequest(BaseModel):
    text: str


@router.get("/current")
async def get_current(store: Store = Depends(get_store)):
    t = store.thermo
    return {"temp": t.current_temp, "humidity": t.current_hum}


@router.get("/minmax")
async def get_minmax(store: Store = Depends(get_store)):
    t = store.thermo
    return {
        "min_temp": t.min_temp,
        "max_temp": t.max_temp,
        "min_hum": t.min_hum,
        "max_hum": t.max_hum,
    }


@router.post("/reset")
async def reset_thermo(device: DeviceManager = Depends(get_device)):
    frame = CanFramePacket(arb_id=THERMO_RESET_ID, dlc=0, data=b"")
    device.send_packet(frame)
    return {"status": "ok"}


@router.post("/text")
async def send_text(req: TextRequest, device: DeviceManager = Depends(get_device)):
    frames = encode_thermo_text(req.text)
    for frame in frames:
        device.send_packet(frame)
    return {"status": "ok", "frames_sent": len(frames)}
