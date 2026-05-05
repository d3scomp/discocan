import { LitElement, css, html, svg } from "lit";
import { customElement, state } from "lit/decorators.js";
import { onWsEvent } from "../ws";
import {
  getPunchpressGeometry,
  getPunchpressPunches,
  getPunchpressStatus,
  restartSim,
  sendFrame,
  setPunchpressAutoRun,
} from "../api";

const PUNCHPRESS_COMMAND_CAN_ID = 0x202;
const PUNCHPRESS_COMMAND_HOME = 0x00;
const PUNCHPRESS_COMMAND_MOVE_TO = 0x01;
const PUNCHPRESS_COMMAND_PUNCH_AT = 0x02;
const ENCODER_TICKS_PER_MM = 10;

interface PunchpressStatus {
  x: number;
  y: number;
  head_up: boolean;
  fail: boolean;
  border_top: boolean;
  border_bottom: boolean;
  border_left: boolean;
  border_right: boolean;
  last_update?: number | null;
}

interface PunchEntry {
  timestamp: number;
  x: number;
  y: number;
}

interface Geometry {
  work_area_width_mm: number;
  work_area_height_mm: number;
  border_zone_mm: number;
}

const DEFAULT_GEO: Geometry = {
  work_area_width_mm: 2000,
  work_area_height_mm: 1500,
  border_zone_mm: 100,
};

/** 50-point circle around the safe-zone centre, in mm (for visualization
 * only — the server owns the canonical target list and the sequence logic). */
function buildAutoTargetsMm(geo: Geometry): Array<[number, number]> {
  const cx = geo.work_area_width_mm / 2 + geo.border_zone_mm;
  const cy = geo.work_area_height_mm / 2 + geo.border_zone_mm;
  const rMm = 500;
  const targets: Array<[number, number]> = [];
  for (let i = 0; i < 50; i++) {
    const a = (2 * Math.PI * i) / 50;
    targets.push([cx + rMm * Math.cos(a), cy + rMm * Math.sin(a)]);
  }
  return targets;
}

/** SVG-unit size of head and punch squares (viewBox is 400x300). */
const HEAD_SIZE = 4;

function fmtTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

@customElement("punchpress-widget")
export class PunchpressWidget extends LitElement {
  static styles = css`
    :host {
      display: flex;
      flex-direction: row;
      gap: 0.6rem;
      height: 100%;
      min-height: 0;
      font-family: ui-monospace, "SF Mono", Consolas, Menlo, monospace;
      font-size: 0.85rem;
    }
    .canvas-wrap {
      flex: 1 1 auto;
      min-width: 0;
      min-height: 0;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.5rem;
      position: relative;
    }
    svg {
      display: block;
      width: 100%;
      height: 100%;
    }

    .side {
      flex: 0 0 340px;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.6rem;
      min-height: 0;
    }
    h3 {
      color: var(--punch);
      font-size: 0.95rem;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px 12px;
    }
    .grid .label { color: var(--text-dim); }
    .grid .val { color: var(--text); text-align: right; font-feature-settings: "tnum"; }
    .grid .val.ok    { color: var(--rx); }
    .grid .val.warn  { color: var(--warn); }
    .grid .val.fail  { color: var(--error); font-weight: bold; }
    .grid .val.busy  { color: var(--warn); }

    .borders {
      display: flex;
      gap: 4px;
    }
    .borders .b {
      flex: 1;
      text-align: center;
      padding: 3px 0;
      border: 1px solid var(--border);
      border-radius: 3px;
      color: var(--text-dim);
      background: var(--bg);
      font-size: 0.78rem;
      letter-spacing: 0.05em;
    }
    .borders .b.on {
      color: var(--bg);
      background: var(--warn);
      border-color: var(--warn);
      font-weight: bold;
    }

    .row {
      display: flex;
      gap: 0.4rem;
    }
    .row input {
      flex: 1;
      background: var(--bg-input);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 5px 8px;
      border-radius: 3px;
      font: inherit;
      min-width: 0;
    }
    .row button {
      flex: 1;
      padding: 5px 12px;
      border-radius: 3px;
      cursor: pointer;
      font: inherit;
      border: none;
      color: white;
      font-weight: 600;
    }
    .row button:hover { filter: brightness(1.15); }
    .btn-home   { background: #2d6a9f; }
    .btn-move   { background: #2d8b9f; }
    .btn-punch  { background: var(--punch); color: var(--bg); }
    .btn-sim    { background: #9f5a2d; }
    .btn-auto   { background: var(--success); }
    .btn-auto.running { background: var(--error); }

    .punch-list {
      flex: 1 1 auto;
      min-height: 80px;
      overflow-y: auto;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 3px;
      padding: 4px 6px;
      font-size: 0.78rem;
    }
    .punch-list .empty {
      color: var(--text-dim);
      font-style: italic;
    }
    .punch-list .entry {
      display: flex;
      gap: 8px;
      color: var(--text);
      font-feature-settings: "tnum";
      padding: 1px 0;
    }
    .punch-list .entry .ts { color: var(--text-dim); }
    .punch-list .entry .xy { color: var(--punch); }
    .punch-header {
      color: var(--text-dim);
      font-size: 0.78rem;
      letter-spacing: 0.04em;
    }
  `;

  @state() private status: PunchpressStatus | null = null;
  @state() private punches: PunchEntry[] = [];
  @state() private geo: Geometry = DEFAULT_GEO;
  @state() private controllerBusy: boolean | null = null;
  @state() private autoActive = false;
  @state() private autoIndex = 0;
  @state() private autoTotal = 50;

  private _autoTargetsMm: Array<[number, number]> = buildAutoTargetsMm(DEFAULT_GEO);

  private _xInput = "";
  private _yInput = "";

  connectedCallback() {
    super.connectedCallback();
    onWsEvent("punchpress_status", (d) => {
      this.status = d as PunchpressStatus;
    });
    onWsEvent("punchpress_punch", (d) => {
      this.punches = [...this.punches.slice(-499), d as PunchEntry];
    });
    onWsEvent("punchpress_controller_status", (d) => {
      this.controllerBusy = Boolean(d.busy);
    });
    onWsEvent("punchpress_auto_run", (d) => {
      this.autoActive = Boolean(d.active);
      this.autoIndex = Number(d.index ?? 0);
      this.autoTotal = Number(d.total ?? this.autoTotal);
    });

    getPunchpressGeometry()
      .then((g: Geometry) => {
        this.geo = g;
        this._autoTargetsMm = buildAutoTargetsMm(g);
      })
      .catch(() => {});
    getPunchpressStatus()
      .then((s) => {
        if (s && s.last_update !== null) this.status = s;
      })
      .catch(() => {});
    getPunchpressPunches()
      .then((ps) => (this.punches = ps))
      .catch(() => {});
  }

  // ── command helpers ──────────────────────────────────────────────────────

  private async _sendCommand(cmd: number, xTicks: number, yTicks: number) {
    const x = Math.max(0, Math.min(0xffff, xTicks));
    const y = Math.max(0, Math.min(0xffff, yTicks));
    const data = [cmd, (x >> 8) & 0xff, x & 0xff, (y >> 8) & 0xff, y & 0xff];
    await sendFrame(PUNCHPRESS_COMMAND_CAN_ID, data);
  }

  private _readXY(): [number, number] | null {
    if (!this._xInput.trim() || !this._yInput.trim()) return null;
    const x = parseFloat(this._xInput);
    const y = parseFloat(this._yInput);
    if (isNaN(x) || isNaN(y)) return null;
    return [x, y];
  }

  private async _sendHome() {
    await this._sendCommand(PUNCHPRESS_COMMAND_HOME, 0, 0);
  }

  private async _sendMove() {
    const xy = this._readXY();
    if (xy === null) return;
    await this._sendCommand(
      PUNCHPRESS_COMMAND_MOVE_TO,
      Math.round(xy[0] * ENCODER_TICKS_PER_MM),
      Math.round(xy[1] * ENCODER_TICKS_PER_MM),
    );
  }

  private async _sendPunchAt() {
    const xy = this._readXY();
    if (xy === null) return;
    await this._sendCommand(
      PUNCHPRESS_COMMAND_PUNCH_AT,
      Math.round(xy[0] * ENCODER_TICKS_PER_MM),
      Math.round(xy[1] * ENCODER_TICKS_PER_MM),
    );
  }

  private async _sendSimRestart() {
    const xy = this._readXY();
    const xAbs = xy ? xy[0] + this.geo.border_zone_mm : null;
    const yAbs = xy ? xy[1] + this.geo.border_zone_mm : null;
    // Server clears its auto-run state on restart and broadcasts the new
    // state, so we don't touch autoActive locally — just send.
    await restartSim(xAbs, yAbs);
    this._xInput = "";
    this._yInput = "";
    this.punches = [];
    this.requestUpdate();
  }

  private async _toggleAuto() {
    // Server owns the state machine; we just request the desired toggle and
    // reflect the resulting punchpress_auto_run event in the UI.
    await setPunchpressAutoRun(!this.autoActive);
  }

  // ── render ──────────────────────────────────────────────────────────────

  private _renderSvg() {
    const totalW = this.geo.work_area_width_mm + 2 * this.geo.border_zone_mm;
    const totalH = this.geo.work_area_height_mm + 2 * this.geo.border_zone_mm;
    const W = 400;
    const H = 300;
    const sx = (mm: number) => (mm / totalW) * W;
    const sy = (mm: number) => H - (mm / totalH) * H;

    const innerX0 = sx(this.geo.border_zone_mm);
    const innerY0 = sy(this.geo.border_zone_mm + this.geo.work_area_height_mm);
    const innerW = sx(this.geo.border_zone_mm + this.geo.work_area_width_mm) - innerX0;
    const innerH = sy(this.geo.border_zone_mm) - innerY0;

    const s = this.status;
    const headColor = s
      ? s.fail ? "#f85149" : s.head_up ? "#56d364" : "#d29922"
      : "#8b949e";

    const half = HEAD_SIZE / 2;

    return html`
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
        <!-- Border zone (full sim area) -->
        <rect x="0" y="0" width="${W}" height="${H}" fill="#0a0e16" stroke="#30363d"/>
        <!-- Safe zone -->
        <rect
          x="${innerX0}" y="${innerY0}"
          width="${innerW}" height="${innerH}"
          fill="#10141d"
          stroke="#3b424b"
          stroke-dasharray="3,3"
        />

        <!-- Auto-run targets preview (under punches) -->
        ${this.autoActive
          ? this._autoTargetsMm.map((t, i) => {
              const done = i < this.autoIndex;
              const next = i === this.autoIndex;
              return svg`
                <circle
                  cx="${sx(t[0])}" cy="${sy(t[1])}"
                  r="${next ? 3 : 1.5}"
                  fill="${next ? "#58a6ff" : "transparent"}"
                  stroke="${next ? "#58a6ff" : "#3b424b"}"
                  stroke-width="${next ? 1 : 0.6}"
                  opacity="${done ? 0.25 : 0.85}"
                />
              `;
            })
          : ""}

        <!-- Punches: filled squares the size of the head -->
        ${this.punches.map(
          (p) => svg`
            <rect
              x="${sx(p.x) - half}" y="${sy(p.y) - half}"
              width="${HEAD_SIZE}" height="${HEAD_SIZE}"
              fill="#c77dff" opacity="0.75"
            />
          `,
        )}

        <!-- Head: thick outline square -->
        ${s
          ? svg`
              <rect
                x="${sx(s.x) - half}" y="${sy(s.y) - half}"
                width="${HEAD_SIZE}" height="${HEAD_SIZE}"
                fill="none"
                stroke="${headColor}"
                stroke-width="2"
                vector-effect="non-scaling-stroke"
              />
            `
          : ""}
      </svg>
    `;
  }

  private _renderPunchList() {
    if (this.punches.length === 0) {
      return html`<div class="empty">No punches yet</div>`;
    }
    // Newest first.
    const items = [...this.punches].reverse();
    return items.map((p) => {
      const xRel = (p.x - this.geo.border_zone_mm).toFixed(1);
      const yRel = (p.y - this.geo.border_zone_mm).toFixed(1);
      return html`
        <div class="entry">
          <span class="ts">${fmtTimestamp(p.timestamp)}</span>
          <span class="xy">(${xRel}, ${yRel}) mm</span>
        </div>
      `;
    });
  }

  render() {
    const s = this.status;
    const fmt = (v: number | null | undefined) =>
      v == null ? "—" : v.toFixed(1);

    const headLabel = s ? (s.fail ? "FAIL" : s.head_up ? "UP" : "DOWN") : "—";
    const headClass = s ? (s.fail ? "fail" : s.head_up ? "ok" : "warn") : "";

    const xRel = s ? s.x - this.geo.border_zone_mm : null;
    const yRel = s ? s.y - this.geo.border_zone_mm : null;

    const ctrlLabel = this.controllerBusy === null
      ? "—"
      : this.controllerBusy ? "BUSY" : "idle";
    const ctrlClass = this.controllerBusy === null
      ? ""
      : this.controllerBusy ? "busy" : "ok";

    return html`
      <div class="canvas-wrap">${this._renderSvg()}</div>

      <aside class="side">
        <h3>Punchpress</h3>

        <div class="grid">
          <span class="label">X / Y</span>
          <span class="val">${fmt(xRel)} / ${fmt(yRel)} mm</span>

          <span class="label">Head</span>
          <span class="val ${headClass}">${headLabel}</span>

          <span class="label">Controller</span>
          <span class="val ${ctrlClass}">${ctrlLabel}</span>

          <span class="label">Punches</span>
          <span class="val">${this.punches.length}</span>

          ${this.autoActive
            ? html`
                <span class="label">Auto run</span>
                <span class="val">${this.autoIndex} / ${this.autoTotal}</span>
              `
            : ""}
        </div>

        <div class="borders">
          <span class="b ${s?.border_top ? "on" : ""}">TOP</span>
          <span class="b ${s?.border_bottom ? "on" : ""}">BOT</span>
          <span class="b ${s?.border_left ? "on" : ""}">L</span>
          <span class="b ${s?.border_right ? "on" : ""}">R</span>
        </div>

        <div class="row">
          <input
            placeholder="X (mm, safe-zone)"
            .value=${this._xInput}
            @input=${(e: Event) => (this._xInput = (e.target as HTMLInputElement).value)}
          />
          <input
            placeholder="Y (mm, safe-zone)"
            .value=${this._yInput}
            @input=${(e: Event) => (this._yInput = (e.target as HTMLInputElement).value)}
          />
        </div>

        <div class="row">
          <button class="btn-home" @click=${this._sendHome}>Home</button>
          <button class="btn-move" @click=${this._sendMove}>Move</button>
          <button class="btn-punch" @click=${this._sendPunchAt}>Punch At</button>
        </div>

        <div class="row">
          <button class="btn-sim" @click=${this._sendSimRestart}>Sim Restart</button>
          <button
            class="btn-auto ${this.autoActive ? "running" : ""}"
            @click=${this._toggleAuto}
          >${this.autoActive ? "Stop Auto" : "Auto Run"}</button>
        </div>

        <div class="punch-header">Punches (newest first)</div>
        <div class="punch-list">${this._renderPunchList()}</div>
      </aside>
    `;
  }
}
