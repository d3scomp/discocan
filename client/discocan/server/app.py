"""FastAPI application factory."""

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from discocan.config import (
    PUNCHPRESS_CONTROLLER_STATUS_CAN_ID,
    PUNCHPRESS_CTRL_STATUS_BUSY_BIT,
    THERMO_CURRENT_ID,
    THERMO_MINMAX_ID,
)
from discocan.device import DeviceManager
from discocan.event_bus import EventBus
from discocan.protocol import (
    CanFramePacket,
    CanTxFramePacket,
    SimulationPunchPacket,
    SimulationStatusPacket,
)
from discocan.punchpress_auto import PunchpressAutoRun
from discocan.store import Store

from .routes import can as can_routes
from .routes import punchpress as punchpress_routes
from .routes import thermo as thermo_routes


def create_app(
    device: DeviceManager,
    store: Store,
    bus: EventBus,
    auto_run: PunchpressAutoRun,
) -> FastAPI:
    app = FastAPI(title="discocan", version="0.1.0")

    # Init route modules with shared singletons
    can_routes.init(device)
    thermo_routes.init(device, store)
    punchpress_routes.init(device, store, auto_run)

    app.include_router(can_routes.router)
    app.include_router(thermo_routes.router)
    app.include_router(punchpress_routes.router)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        import asyncio as _asyncio

        await ws.accept()
        # Snapshot current state for late subscribers — connection_state and
        # punchpress_auto_run are only broadcast on transition, so a client
        # connecting after either changed would otherwise miss the value.
        await ws.send_json({"type": "connection_state", "state": device.current_state})
        await ws.send_json({"type": "punchpress_auto_run", **auto_run.state})
        q = await bus.subscribe()
        try:
            while True:
                event = await q.get()
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        except _asyncio.CancelledError:
            # Shutdown path. Don't re-raise — that would surface as
            # "Exception in ASGI application" in uvicorn logs.
            pass
        except Exception:
            pass
        finally:
            bus.unsubscribe(q)

    @app.get("/api/connection_state")
    async def get_connection_state():
        return {"state": device.current_state}

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


def make_packet_handler(store: Store, bus: EventBus, auto_run: PunchpressAutoRun):
    """Return a callback that processes incoming packets into store + event bus."""

    def handle(packet):
        ts = time.time()

        if isinstance(packet, (CanFramePacket, CanTxFramePacket)):
            direction = "tx" if isinstance(packet, CanTxFramePacket) else "rx"

            event: dict = {
                "type": "can_frame",
                "direction": direction,
                "timestamp": ts,
                "fw_timestamp_ms": packet.timestamp_ms,
                "id": packet.arb_id,
                "dlc": packet.dlc,
                "data": list(packet.data),
            }

            # Decode thermometer frames (only rx — tx 0x100/0x101 would mean
            # the firmware echoed our own command, which we don't expect).
            if direction == "rx":
                if packet.arb_id == PUNCHPRESS_CONTROLLER_STATUS_CAN_ID and packet.dlc >= 1:
                    busy = bool(packet.data[0] & PUNCHPRESS_CTRL_STATUS_BUSY_BIT)
                    bus.publish_sync({
                        "type": "punchpress_controller_status",
                        "busy": busy,
                    })
                    auto_run.on_controller_status(busy)

                if packet.arb_id == THERMO_CURRENT_ID and packet.dlc == 4:
                    raw_temp = (packet.data[0] << 8) | packet.data[1]
                    raw_hum = (packet.data[2] << 8) | packet.data[3]
                    store.update_thermo_current(raw_temp, raw_hum)
                    thermo_event = {
                        "type": "thermo_current",
                        "temp": store.thermo.current_temp,
                        "humidity": store.thermo.current_hum,
                    }
                    bus.publish_sync(thermo_event)

                elif packet.arb_id == THERMO_MINMAX_ID and packet.dlc == 8:
                    raw_min_temp = (packet.data[0] << 8) | packet.data[1]
                    raw_min_hum = (packet.data[2] << 8) | packet.data[3]
                    raw_max_temp = (packet.data[4] << 8) | packet.data[5]
                    raw_max_hum = (packet.data[6] << 8) | packet.data[7]
                    store.update_thermo_minmax(raw_min_temp, raw_min_hum, raw_max_temp, raw_max_hum)
                    minmax_event = {
                        "type": "thermo_minmax",
                        "min_temp": store.thermo.min_temp,
                        "max_temp": store.thermo.max_temp,
                        "min_hum": store.thermo.min_hum,
                        "max_hum": store.thermo.max_hum,
                    }
                    bus.publish_sync(minmax_event)

            bus.publish_sync(event)

        elif isinstance(packet, SimulationStatusPacket):
            store.update_punchpress_status(
                packet.x_100um, packet.y_100um, packet.status_bits, ts
            )
            pp = store.punchpress
            bus.publish_sync({
                "type": "punchpress_status",
                "timestamp": ts,
                "x": pp.x_mm,
                "y": pp.y_mm,
                "head_up": pp.head_up,
                "fail": pp.fail,
                "border_top": pp.border_top,
                "border_bottom": pp.border_bottom,
                "border_left": pp.border_left,
                "border_right": pp.border_right,
            })

        elif isinstance(packet, SimulationPunchPacket):
            store.add_punch(packet.x_100um, packet.y_100um, ts)
            bus.publish_sync({
                "type": "punchpress_punch",
                "timestamp": ts,
                "x": packet.x_100um / 100.0,
                "y": packet.y_100um / 100.0,
            })

    return handle
