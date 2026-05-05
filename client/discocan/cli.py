"""Typer CLI for discocan."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

from discocan.config import DEFAULT_WEB_PORT

app = typer.Typer(
    name="discocan",
    help="CAN bus monitor and control via DISCOCAN USB adapter.",
)


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        asyncio.run(_run(
            port=None,
            web_port=DEFAULT_WEB_PORT,
            with_tui=True,
        ))


# ── tui (default) ─────────────────────────────────────────────────────────────


@app.command()
def tui(
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Serial port (auto-detect if omitted)"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port", help="HTTP/WS listen port"),
):
    """Start discocan with the full TUI dashboard (also serves REST + WS).

    This is the default — running `discocan` with no subcommand does the same.
    """
    asyncio.run(_run(port, web_port, with_tui=True))


# ── server (headless) ─────────────────────────────────────────────────────────


@app.command()
def server(
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Serial port (auto-detect if omitted)"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port", help="HTTP/WS listen port"),
):
    """Start discocan as a headless server (REST + WS, no TUI).

    Prints the URL where the web UI is reachable, then runs silently — use
    `discocan can-monitor` or the web UI to watch frames.
    """
    asyncio.run(_run(port, web_port, with_tui=False))


async def _run(
    port: Optional[str],
    web_port: int,
    with_tui: bool,
) -> None:
    import uvicorn
    import serial

    from discocan.config import BAUD_RATE
    from discocan.device import (
        DeviceManager,
        DeviceNotFoundError,
        PortInUseError,
        _is_port_locked_error,
    )
    from discocan.event_bus import EventBus
    from discocan.punchpress_auto import PunchpressAutoRun
    from discocan.server.app import create_app, make_packet_handler
    from discocan.store import Store
    from discocan.tui.app import DiscocanApp

    # Windows ProactorEventLoop logs a noisy traceback when a peer forcibly
    # closes a connection (WinError 10054) — the asyncio default handler reports
    # ConnectionResetError raised inside _call_connection_lost. Nothing the app
    # can act on; swallow it but defer everything else to the default handler.
    def _exc_filter(loop: asyncio.AbstractEventLoop, ctx: dict) -> None:
        if isinstance(ctx.get("exception"), ConnectionResetError):
            return
        loop.default_exception_handler(ctx)

    asyncio.get_running_loop().set_exception_handler(_exc_filter)

    try:
        device = DeviceManager(port)
    except DeviceNotFoundError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)

    # Pre-flight: try opening the port BEFORE the TUI takes over the terminal.
    # If it's locked we'd otherwise fail inside an async task and any error
    # message would get swallowed by Textual's screen capture.
    try:
        resolved_port = device._resolve_port()
        _probe = serial.Serial(resolved_port, BAUD_RATE, timeout=0.1)
        _probe.close()
    except serial.SerialException as e:
        if _is_port_locked_error(e):
            typer.echo(
                f"[error] Cannot open {resolved_port}: another discocan server is likely already running. "
                "Stop it first.",
                err=True,
            )
            raise typer.Exit(1)
        # other serial error — let the device's reconnect loop handle it

    store = Store()
    bus = EventBus()
    auto_run = PunchpressAutoRun(device, bus)

    device.set_handler(make_packet_handler(store, bus, auto_run))
    device.set_state_handler(lambda state: bus.publish_sync({"type": "connection_state", "state": state}))

    fastapi_app = create_app(device, store, bus, auto_run)
    uvi_config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=web_port,
        log_level="warning",
        ws="wsproto",
        # Don't wait forever for stuck clients (e.g. dangling WebSocket) when
        # Ctrl-C is pressed; force-close after this many seconds.
        timeout_graceful_shutdown=2,
    )
    uvi_server = uvicorn.Server(uvi_config)

    device_task = asyncio.create_task(device.run(), name="device")
    uvicorn_task = asyncio.create_task(uvi_server.serve(), name="uvicorn")
    tasks = [device_task, uvicorn_task]

    if with_tui:
        tui_app = DiscocanApp(device, store, bus, auto_run)
        tasks.append(asyncio.create_task(tui_app.run_async(), name="tui"))
    else:
        typer.echo(f"discocan listening on http://localhost:{web_port}  (Ctrl-C to stop)")

    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        pass

    # If the device task ended with PortInUseError, surface it as a clean exit.
    port_in_use_msg: Optional[str] = None
    if device_task.done() and not device_task.cancelled():
        exc = device_task.exception()
        if isinstance(exc, PortInUseError):
            port_in_use_msg = str(exc)

    # Tear everything down. Uvicorn's lifespan task and asyncio's own
    # exception handler unconditionally log CancelledError tracebacks during
    # shutdown — partly during our gather, partly later when asyncio.run
    # closes the loop and reports unretrieved task exceptions. We have no
    # useful output to keep past this point, so silence logging for the rest
    # of the process and also install a no-op asyncio exception handler so
    # nothing surfaces during loop close. typer.echo writes go to stderr
    # directly and are unaffected.
    import logging
    logging.disable(logging.CRITICAL)
    asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: None)

    pending = [t for t in tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    if port_in_use_msg is not None:
        typer.echo(f"[error] {port_in_use_msg}", err=True)
        raise typer.Exit(1)


# ── list-ports ───────────────────────────────────────────────────────────────


@app.command("list-ports")
def list_ports():
    """List all available COM ports with full metadata."""
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        typer.echo("No COM ports found.")
        return
    fields = [
        ("device",        "Device"),
        ("name",          "Name"),
        ("description",   "Description"),
        ("hwid",          "HWID"),
        ("vid",           "VID"),
        ("pid",           "PID"),
        ("serial_number", "Serial number"),
        ("location",      "Location"),
        ("manufacturer",  "Manufacturer"),
        ("product",       "Product"),
        ("interface",     "Interface"),
    ]
    from discocan.config import DEVICE_PID, DEVICE_VID
    for p in sorted(ports, key=lambda x: x.device):
        is_discocan = p.vid == DEVICE_VID and p.pid == DEVICE_PID
        marker = " <-- DISCOCAN" if is_discocan else ""
        typer.echo("-" * 40)
        typer.echo(f"  {'Device':<16} {p.device}{marker}")
        for attr, label in fields[1:]:  # skip device, already printed
            val = getattr(p, attr, None)
            if val is not None:
                typer.echo(f"  {label:<16} {val}")


# ── can-send ──────────────────────────────────────────────────────────────────


@app.command("can-send")
def can_send(
    can_id: str = typer.Argument(..., help="CAN ID in hex (e.g. 0x100 or 100)"),
    data: list[str] = typer.Argument(default=None, help="Data bytes in hex (e.g. DE AD BE EF)"),
    host: str = typer.Option("localhost", "--host"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port"),
):
    """Send a CAN frame to a running discocan server."""
    import httpx

    arb_id = int(can_id, 16)
    data_bytes = [int(b, 16) for b in (data or [])]
    url = f"http://{host}:{web_port}/api/can/send"
    try:
        r = httpx.post(url, json={"id": arb_id, "data": data_bytes}, timeout=5)
        r.raise_for_status()
        typer.echo(r.json())
    except httpx.ConnectError:
        typer.echo(f"[error] Cannot connect to {url}. Is the server running?", err=True)
        raise typer.Exit(1)


# ── can-monitor ───────────────────────────────────────────────────────────────


@app.command("can-monitor")
def can_monitor(
    host: str = typer.Option("localhost", "--host"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port"),
):
    """Stream CAN frames from a running server via WebSocket."""
    try:
        asyncio.run(_ws_monitor(host, web_port))
    except KeyboardInterrupt:
        typer.echo("\nStopped.")


async def _ws_monitor(host: str, web_port: int) -> None:
    import websockets

    url = f"ws://{host}:{web_port}/ws"
    typer.echo(f"Connecting to {url} …")
    try:
        async with websockets.connect(url) as ws:
            async for message in ws:
                import json
                event = json.loads(message)
                if event.get("type") == "can_frame":
                    d = event["direction"].upper()
                    arb_id = event["id"]
                    dlc = event["dlc"]
                    data_str = " ".join(f"{b:02X}" for b in event["data"])
                    print(f"{d}  0x{arb_id:03X}  DLC={dlc}  [{data_str}]", flush=True)
                else:
                    import json as _json
                    print(_json.dumps(event), flush=True)
    except (OSError, websockets.exceptions.WebSocketException) as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)


# ── thermo-reset ──────────────────────────────────────────────────────────────


@app.command("thermo-reset")
def thermo_reset(
    host: str = typer.Option("localhost", "--host"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port"),
):
    """Send a thermometer reset command to a running server."""
    import httpx

    url = f"http://{host}:{web_port}/api/thermo/reset"
    try:
        r = httpx.post(url, timeout=5)
        r.raise_for_status()
        typer.echo(r.json())
    except httpx.ConnectError:
        typer.echo(f"[error] Cannot connect to {url}. Is the server running?", err=True)
        raise typer.Exit(1)


# ── thermo-text ───────────────────────────────────────────────────────────────


@app.command("thermo-text")
def thermo_text(
    text: Optional[str] = typer.Argument(None, help="Text to send (use \\n for newline)"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read text from file"),
    host: str = typer.Option("localhost", "--host"),
    web_port: int = typer.Option(DEFAULT_WEB_PORT, "--web-port"),
):
    """Send text to the thermometer display via a running server."""
    import httpx

    if file is not None:
        content = file.read_text()
    elif text is not None:
        content = text.replace("\\n", "\n")
    else:
        typer.echo("[error] Provide text argument or --file", err=True)
        raise typer.Exit(1)

    url = f"http://{host}:{web_port}/api/thermo/text"
    try:
        r = httpx.post(url, json={"text": content}, timeout=5)
        r.raise_for_status()
        typer.echo(r.json())
    except httpx.ConnectError:
        typer.echo(f"[error] Cannot connect to {url}. Is the server running?", err=True)
        raise typer.Exit(1)
