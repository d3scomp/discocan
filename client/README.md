# DISCOCAN

CAN-bus monitor and lab tool for the **DISCOCAN** USB-CAN adapter — an
STM32F407 Discovery board running custom firmware that bridges a 500 kbit/s
CAN bus to USB CDC, simulates a 2-axis punchpress, and serves as the
host-side dashboard for the embedded-systems lab (NSWE001 at the Charles
University). Provides a terminal UI, a web dashboard, and a small CLI in one Python package. 

## Install

```bash
pipx install discocan
```

The `discocan` command becomes available system-wide.

## Quick start

Plug the DISCOCAN adapter into USB (it enumerates as STM32 CDC, VID `0x0483`
PID `0x5740`), then:

```bash
discocan          # default — TUI + REST + WS on :8765
discocan tui      # explicit (same as above)
discocan server   # headless: REST + WS only
```

Open <http://localhost:8765/> for the web dashboard.

Other CLI commands:

```bash
discocan list-ports                # list serial ports, mark the DISCOCAN
discocan can-send 0x123 DE AD      # send a CAN frame (talks to running server)
discocan can-monitor               # stream frames from a running server
discocan thermo-reset
discocan thermo-text "hello\nworld"
```

## TUI hotkeys

| Key       | Action                                              |
|-----------|-----------------------------------------------------|
| F5/F6/F7  | switch CAN trace / Thermometer / Punchpress         |
| Ctrl+A    | toggle autoscroll                                   |
| Ctrl+S    | start / stop trace                                  |
| Ctrl+T    | hide TX frames                                      |
| Ctrl+U    | hide punchpress status (`0x200`) frames             |
| `?`       | show hotkeys                                        |
| `q`       | quit                                                |

## Lab setup

A typical lab bench has two CAN nodes on a shared two-wire bus:

```
   ┌──────────────┐        ┌───────────────────────────┐
   │   DISCOCAN   │  CANH  │       S32 board           │
   │ (STM32F407)  │────────│ punchpress or thermometer │
   │              │  CANL  │       controller          │
   └──────┬───────┘        └───────────────────────────┘
          │ USB
          ▼
       host PC running `discocan`
```

Bus parameters: **500 kbit/s, standard 11-bit IDs, no remote frames,
no CAN-FD**.

| Side                        | CAN_TX | CAN_RX | CAN_STB |
|-----------------------------|--------|--------|---------|
| DISCOCAN (STM32F407)        | PD1    | PB8    | PD3     |
| S32 controller (S32K144)    | PTC3   | PTC2   | PTD7    |

The host receives a stamped copy of every frame on the bus (RX direction),
plus a stamped copy of every frame the firmware itself transmits (TX
direction); see "USB framing" below.

## CAN frame reference

All IDs are 11-bit standard. Direction is from the perspective of the
**student-written controller** (i.e., RX = controller listens, TX =
controller sends).

| ID       | Dir on controller        | DLC  | Sender                        | Listeners                         |
|----------|--------------------------|------|-------------------------------|-----------------------------------|
| `0x020`  | TX (test)                | any  | anyone                        | DISCOCAN firmware (echo)          |
| `0x021`  | RX (test response)       | =0x020 | DISCOCAN firmware           | the sender                        |
| `0x100`  | TX (thermo only)         | 4    | thermometer controller        | DISCOCAN host                     |
| `0x101`  | TX (thermo only)         | 8    | thermometer controller        | DISCOCAN host                     |
| `0x102`  | RX (thermo only)         | 0    | DISCOCAN host                 | thermometer controller            |
| `0x103`  | RX (thermo only)         | 1..8 | DISCOCAN host                 | thermometer controller            |
| `0x200`  | RX (punchpress only)     | 1    | DISCOCAN firmware (sim)       | punchpress controller, host       |
| `0x201`  | TX (punchpress only)     | 1    | punchpress controller         | DISCOCAN firmware (sim), host     |
| `0x202`  | RX (punchpress only)     | ≥5   | DISCOCAN host                 | punchpress controller             |
| `0x203`  | TX (punchpress only)     | 1    | punchpress controller         | DISCOCAN host                     |

The DISCOCAN firmware accepts all standard frames into its CAN1 RX FIFO0
and forwards every received frame to the USB host as a CAN_FRAME packet
(direction = `rx`). Every frame the firmware itself transmits is
additionally mirrored to the host as a CAN_TX_FRAME packet (direction =
`tx`), so the trace always reflects what is actually on the wire.

### `0x020 / 0x021` — Echo (debug helper)

If the firmware sees any frame on `0x020`, it immediately retransmits the
same payload on `0x021`. Useful for verifying that a freshly-flashed
controller is actually on the bus and that bitrate / wiring are correct.

* Send any byte sequence (DLC 0–8) on `0x020`.
* Expect the identical payload back on `0x021` within ~1 ms.

The firmware also prints `ECHO: ID=0x020 -> 0x021 DLC=N` to its USB VCP
debug stream, so you can confirm the bridge from the host side too.

### `0x100 / 0x101 / 0x102 / 0x103` — Thermometer

The thermometer controller reads an **SHT3x** humidity/temperature sensor
(or any source with the same scaling) and publishes raw 16-bit readings
in big-endian byte order. The host decodes them as

```
T_celsius   = -45 + 175 * raw / 65535
H_percent   =  -6 + 125 * raw / 65535
```

so `raw = 0x0000` ≈ −45 °C / −6 % and `raw = 0xFFFF` ≈ 130 °C / 119 %.

#### `0x100` — current measurement (DLC = 4)

Send roughly once per second.

| Byte | Field        |
|------|--------------|
| 0    | T_raw[15:8]  |
| 1    | T_raw[7:0]   |
| 2    | H_raw[15:8]  |
| 3    | H_raw[7:0]   |

#### `0x101` — min/max envelope (DLC = 8)

Send whenever any of the four values change, or with the same cadence as
`0x100`. Min / max are tracked since power-on or last `0x102` reset.

| Byte | Field          |
|------|----------------|
| 0–1  | T_min_raw (BE) |
| 2–3  | H_min_raw (BE) |
| 4–5  | T_max_raw (BE) |
| 6–7  | H_max_raw (BE) |

#### `0x102` — reset min/max (DLC = 0)

Empty payload. On receipt the controller should set both min and max to the
current reading.

#### `0x103` — text to display (DLC = 1..8)

The host fragments a string of up to 8-byte chunks. Each byte carries one
ASCII character in the lower 7 bits; bit 7 is set on the **first character
of every line**, so the receiver can tell when to wrap to a new row on
its display:

```
bit 7   = 1 if this character is the first of a new line, else 0
bits 0-6 = ASCII codepoint
```

### `0x200 / 0x201 / 0x202 / 0x203` — Punchpress

The DISCOCAN firmware contains a 2-axis punchpress simulator. The
controller drives it via two PWM "motor" signals and reads back position
through quadrature encoders and four limit switches (see "Punchpress
hardware interface" below). Most of the loop is therefore pin-level, not
CAN — but four CAN frames coordinate punching and host commands.

#### `0x200` — punchpress status (DLC = 1, every 100 ms)

Bit-packed status from the punchpress (firmware → bus). The host also
receives this directly from the firmware over USB, so listening on the bus
is optional for the controller.

| Bit | Meaning              |
|-----|----------------------|
| 0   | TOP border switch    |
| 1   | BOTTOM border switch |
| 2   | LEFT border switch   |
| 3   | RIGHT border switch  |
| 4   | HEAD_UP (1 = up)     |
| 5   | FAIL                 |

`FAIL` is latched by the punchpress if the head leaves the punchpress area
(safe zone + border zone) **or** if the head is moving while down. Once
set, only a sim restart clears it. While in `FAIL`, the punchpress simulation is suspended.

The physical border switches are also driven on dedicated GPIO pins, so
the controller does not strictly need this frame to detect borders.

#### `0x201` — punch request (DLC = 1)

Single-byte command from the controller to the simulator.

| `data[0]` | Meaning                                |
|-----------|----------------------------------------|
| `0x00`    | release punch — head retracts in 200 ms |
| `0x01`    | press punch — head goes down            |

The simulator enforces "no motion while head is down" — if the controller
moves the head with the punch asserted, the simulator latches `FAIL`.

The controller normally re-sends this frame periodically (e.g. every
100 ms) so a missed transition does not jam the head.

#### `0x202` — host command (DLC ≥ 5)

The host (web button or `discocan` CLI / TUI) sends manual or scripted
commands to the controller.

| Byte | Field                                                |
|------|------------------------------------------------------|
| 0    | command: `0x00` HOME, `0x01` MOVE_TO, `0x02` PUNCH_AT |
| 1–2  | x in encoder ticks, big-endian uint16                |
| 3–4  | y in encoder ticks, big-endian uint16                |

10 encoder ticks = 1 mm. After homing, ticks (0, 0) corresponds to the
bottom-left corner of the **safe zone** (i.e. 100 mm of border still
exists in each direction beyond that). Commands are dropped if the
controller is busy executing the previous one.

#### `0x203` — controller status (DLC = 1, every 100 ms)

Reports back to the host whether the controller is currently executing a
command.

| Bit | Meaning                                          |
|-----|--------------------------------------------------|
| 0   | BUSY (1 = HOMING or running MOVE_TO / PUNCH_AT)  |
| 1–7 | reserved (send 0)                                |

The host's "Auto Run" sequence advances on the falling edge of this bit:
when BUSY transitions 1 → 0, the host knows the previous PUNCH_AT
finished and sends the next target.

## Punchpress hardware interface

The CAN protocol above coordinates *what* to punch; the actual control loop
is pin-level. The DISCOCAN firmware exposes a real-time hardware abstraction
of the simulator on its GPIO + timers, and the controller reads / writes
those pins as if they were a real machine.

```
                     ┌───────────────────────────────┐
                     │       DISCOCAN (STM32F407)    │
                     │ ┌───────────────────────────┐ │
                     │ │  punchpress simulator     │ │
                     │ └─┬───┬───┬───┬───┬───┬─┬─┬─┘ │
                     │   │   │   │   │   │   │ │ │   │
                     │   ENCx_A B  ENCy_A B  BORDER  │ ◄── PWMx,y inputs (TIM2/TIM5)
                     │   │   │   │   │   │   │ │ │   │
                     └───┼───┼───┼───┼───┼───┼─┼─┼───┘
                         ▼   ▼   ▼   ▼   ▼   ▼ ▼ ▼
                     ┌───────────────────────────────┐
                     │         S32 controller        │
                     │ ┌───────────────────────────┐ │
                     │ │ student PD / PID + state  │ │
                     │ └───────────────────────────┘ │
                     └───────────────────────────────┘
                         ▲                   ▲
                       PWMx               PWMy
```

### Encoders

X and Y axes each emit a standard quadrature pair (A leads B for forward
motion). Resolution is **10 ticks/mm**; one full step of the simulator's
position by 0.1 mm produces one transition on the appropriate encoder pin.
Decode either by rising-edge interrupts on A and reading B, or by feeding
the pins to an FTM/QD module. The lab's reference implementation uses
software decoding in a port IRQ.

### Border switches

Four GPIO outputs from the simulator, active **high** when the head is in
the corresponding 100 mm border strip (i.e., outside the work area):

* TOP, BOTTOM, LEFT, RIGHT — each high while in the corresponding strip.
  All four are also packed into the `0x200` CAN frame.

Use them to home the axes (drive toward `BORDER_BOTTOM` ∧ `BORDER_LEFT`
until both go high, then back off until they drop, and zero the encoder
counter there).

### PWM motor inputs (controller → simulator)

The simulator measures one PWM input per axis using STM32 input-capture
in PWM-input mode (TIM2 for X, TIM5 for Y). The driving controller can
use any frequency between roughly 200 Hz and 10 kHz; the lab reference
runs the FTM at **1 kHz**. Duty cycle is interpreted as bidirectional
effort:

| Duty cycle  | Effort |
|-------------|--------|
| ≤ 4.5 %     | −1.0 (full reverse) |
| 50 %        | 0 (idle) |
| ≥ 95.5 %    | +1.0 (full forward) |


### Simulator dynamics (for tuning)

Inside the simulator the per-tick (≈ 1 ms) update for each axis is

```
if |speed| < 0.005 mm/tick AND |effort| < 0.40:
    speed = 0                                    # static deadband
else:
    accel = effort * 1e-5  - speed * 2e-4  - 5e-7 * sign(speed)
    #       ──────────────  ─────────────   ──────────────────
    #       drive             viscous drag    Coulomb friction
    speed += accel
    pos   += speed
```

The student controller therefore sees a plant with both a deadband (must
push effort > 0.4 to start moving from rest) and a Coulomb friction term
(constant resistive force while moving). 

A press (`0x201` data[0] = 1) drops the head — the simulator then keeps
HEAD_UP=0 until 200 ms after the controller releases the punch
(`data[0] = 0`).

### Work area

```
(0,1700) ┌────────────────────────────────────────────┐ (2200, 1700)
         │                                            │
         │    ┌──────────────────────────────────┐    │
         │    │                                  │    │
         │    │            safe zone             │    │
         │    │       2000 × 1500 mm             │    │
         │    │                                  │    │
         │    └──────────────────────────────────┘    │
         │   100 mm border zone all around            │
         │                                            │
   (0,0) └────────────────────────────────────────────┘ (2200, 0)
```

After homing, controller-side encoder coordinate (0, 0) sits at the inner
corner of the safe zone (100 mm in from the simulator origin). Driving
encoder coordinates outside (0, 0)..(20000, 15000) ticks runs the head
into the border zone — borders go active and drag still applies, so
recovery is possible. Going outside the simulator area entirely latches
`FAIL` (bit 5 of `0x200`).

## USB framing (host ↔ DISCOCAN)

The DISCOCAN firmware speaks a small custom packet protocol over USB CDC
(virtual COM port). Each packet is `AA 55 <type> <payload> <crc32>`,
where `crc32` is **CRC-32/MPEG-2** (poly `0x04C11DB7`, init `0xFFFFFFFF`,
no reflection, no final XOR) computed over `<type as little-endian
uint32> | <payload zero-padded to a multiple of 4 bytes>`.

| Type | Direction | Payload                                     |
|------|-----------|---------------------------------------------|
| 0x01 | FW → host | rx CAN frame: `ts_ms u32 | id u32 | dlc u8 | data[8]` |
| 0x02 | host → FW | sim restart: `x_100um i32 | y_100um i32`    |
| 0x03 | FW → host | sim status: `x_100um i32 | y_100um i32 | bits u8` |
| 0x04 | FW → host | sim punch event: `x_100um i32 | y_100um i32` |
| 0x05 | FW → host | tx CAN frame (firmware just transmitted on the bus); same layout as 0x01 |

Type 0x01 is also used by the host to *send* a CAN frame to the bus
(set `ts_ms = 0` — the firmware fills the timestamp on its own outgoing
TX echo). The trace's "tx" entries come exclusively from type 0x05, so
every entry the user sees genuinely corresponds to bytes that left the
firmware on CAN.

`x_100um` and `y_100um` are the simulator's position in 1/100 mm (i.e.,
`mm * 100`), absolute including the border zone.

## Python API

`discocan.protocol` exposes the packet classes (`CanFramePacket`,
`SimulationRestartPacket`, …) and the CRC routine for anyone who wants
to talk to the firmware directly without going through the server.

The REST API (when the server is running on `:8765`) is:

* `GET  /api/can/trace?n=…&direction=…` — recent CAN entries
* `POST /api/can/send` `{id, data:[…]}`
* `GET  /api/thermo/{current,minmax}`
* `POST /api/thermo/{reset,text}`
* `GET  /api/punchpress/{status,punches,geometry,auto-run}`
* `POST /api/punchpress/{restart,auto-run}`
* `GET  /api/connection_state`
* WebSocket `/ws` — newline-delimited JSON events (see source for shape)

## Building from source

```bash
git clone <repo>
cd discocan/client
uv sync                    # Python deps
cd web && npm install      # web deps (only for development)
uv run discocan            # run from source
```

`uv run discocan` works from source even without the npm step, because
the wheel build embeds `discocan/server/static/`. For UI work, use
`cd web && npm run dev` for hot reload — Vite proxies `/api` and `/ws` to
`localhost:8765`.

The Hatchling build hook in `hatch_build.py` runs `npm ci && npm run
build` before assembling a wheel. To skip it (e.g. when iterating
locally), set `DISCOCAN_SKIP_WEB_BUILD=1`.

## Releasing

```bash
cd discocan/client
rm -rf dist
uv build                  # wheel + sdist; the wheel includes the built UI
uv publish                # or: pipx run twine upload dist/*
```

Bump `version` in `pyproject.toml` for each release.

## License

MIT.
