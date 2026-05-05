"""REST routes for punchpress simulation."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from discocan.config import (
    PUNCHPRESS_BORDER_ZONE_MM,
    PUNCHPRESS_WORK_AREA_HEIGHT_MM,
    PUNCHPRESS_WORK_AREA_WIDTH_MM,
)
from discocan.device import DeviceManager
from discocan.protocol import SimulationRestartPacket
from discocan.punchpress_auto import PunchpressAutoRun
from discocan.store import Store

router = APIRouter(prefix="/api/punchpress", tags=["punchpress"])

_device: DeviceManager | None = None
_store: Store | None = None
_auto_run: PunchpressAutoRun | None = None


def init(device: DeviceManager, store: Store, auto_run: PunchpressAutoRun) -> None:
    global _device, _store, _auto_run
    _device = device
    _store = store
    _auto_run = auto_run


def get_device() -> DeviceManager:
    assert _device is not None
    return _device


def get_store() -> Store:
    assert _store is not None
    return _store


def get_auto_run() -> PunchpressAutoRun:
    assert _auto_run is not None
    return _auto_run


class RestartRequest(BaseModel):
    x_mm: float | None = None
    y_mm: float | None = None


class AutoRunRequest(BaseModel):
    active: bool


def _default_position() -> tuple[float, float]:
    return (
        PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_WIDTH_MM / 2,
        PUNCHPRESS_BORDER_ZONE_MM + PUNCHPRESS_WORK_AREA_HEIGHT_MM / 2,
    )


@router.get("/status")
async def get_status(store: Store = Depends(get_store)):
    pp = store.punchpress
    return {
        "x": pp.x_mm,
        "y": pp.y_mm,
        "head_up": pp.head_up,
        "fail": pp.fail,
        "border_top": pp.border_top,
        "border_bottom": pp.border_bottom,
        "border_left": pp.border_left,
        "border_right": pp.border_right,
        "last_update": pp.last_update,
    }


@router.get("/punches")
async def get_punches(store: Store = Depends(get_store)):
    return [
        {"timestamp": p.timestamp, "x": p.x_mm, "y": p.y_mm}
        for p in store.punches
    ]


@router.get("/geometry")
async def get_geometry():
    return {
        "work_area_width_mm": PUNCHPRESS_WORK_AREA_WIDTH_MM,
        "work_area_height_mm": PUNCHPRESS_WORK_AREA_HEIGHT_MM,
        "border_zone_mm": PUNCHPRESS_BORDER_ZONE_MM,
    }


@router.post("/restart")
async def restart(
    req: RestartRequest,
    device: DeviceManager = Depends(get_device),
    store: Store = Depends(get_store),
    auto_run: PunchpressAutoRun = Depends(get_auto_run),
):
    default_x, default_y = _default_position()
    x_mm = req.x_mm if req.x_mm is not None else default_x
    y_mm = req.y_mm if req.y_mm is not None else default_y
    # Sim restart invalidates anything the auto-run sequence is doing.
    auto_run.stop()
    packet = SimulationRestartPacket(
        x_100um=int(x_mm * 100),
        y_100um=int(y_mm * 100),
    )
    device.send_packet(packet)
    store.clear_punches()
    return {"status": "ok", "x_mm": x_mm, "y_mm": y_mm}


@router.get("/auto-run")
async def get_auto_run_state(auto_run: PunchpressAutoRun = Depends(get_auto_run)):
    return auto_run.state


@router.post("/auto-run")
async def set_auto_run_state(
    req: AutoRunRequest,
    auto_run: PunchpressAutoRun = Depends(get_auto_run),
):
    if req.active:
        auto_run.start()
    else:
        auto_run.stop()
    return auto_run.state
