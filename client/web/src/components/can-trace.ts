import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { onWsEvent } from "../ws";
import { sendFrame } from "../api";

interface CANEntry {
  direction: "rx" | "tx";
  timestamp: number;
  fw_timestamp_ms: number | null;
  id: number;
  dlc: number;
  data: number[];
}

const PUNCHPRESS_STATUS_CAN_ID = 0x200;
const MAX_ENTRIES = 300;

function pad(n: number, w: number): string {
  return n.toString().padStart(w, "0");
}

/** Format firmware HAL_GetTick() ms as HH:MM:SS.mmm (boot-relative). */
function formatFwTimestamp(fwMs: number | null | undefined): string {
  if (fwMs == null) return "  --:--:--.---";
  const ms = fwMs % 1000;
  const totalSec = Math.floor(fwMs / 1000);
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

@customElement("can-trace")
export class CanTrace extends LitElement {
  static styles = css`
    :host {
      display: flex;
      flex-direction: column;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.6rem;
      font-family: ui-monospace, "SF Mono", Consolas, Menlo, monospace;
      font-size: 0.85rem;
      min-height: 0;
      height: 100%;
    }
    h3 {
      color: var(--accent);
      margin-bottom: 0.5rem;
      font-size: 0.95rem;
    }
    .toolbar {
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 0.4rem;
    }
    .toolbar button,
    .send-row button {
      background: var(--bg-input);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 4px 10px;
      border-radius: 3px;
      cursor: pointer;
      font: inherit;
    }
    .toolbar button:hover { background: #2d333b; }
    .toolbar button.active {
      background: var(--accent);
      color: var(--bg);
      border-color: var(--accent);
    }
    .toolbar input {
      background: var(--bg-input);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 4px 8px;
      border-radius: 3px;
      flex: 1;
      min-width: 100px;
      font: inherit;
    }
    .toolbar .stats {
      color: var(--text-dim);
      font-size: 0.8rem;
    }

    .table-wrap {
      flex: 1;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 3px;
      background: var(--bg);
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    thead {
      position: sticky;
      top: 0;
      background: var(--bg-card);
      z-index: 1;
    }
    th {
      text-align: left;
      color: var(--text-dim);
      border-bottom: 1px solid var(--border);
      padding: 5px 8px;
      font-weight: normal;
      font-size: 0.78rem;
    }
    td { padding: 1px 8px; vertical-align: top; white-space: nowrap; }
    tr:hover td { background: rgba(255, 255, 255, 0.03); }
    .dir { width: 36px; }
    .dir-rx { color: var(--rx); }
    .dir-tx { color: var(--tx); }
    .ts { color: var(--text-dim); width: 110px; }
    .id-col { color: var(--text); font-weight: bold; width: 60px; }
    .dlc { color: var(--text-dim); width: 32px; }
    .data { font-feature-settings: "tnum"; }

    .send-row {
      margin-top: 0.5rem;
      display: flex;
      gap: 0.4rem;
      align-items: center;
    }
    .send-row input {
      background: var(--bg-input);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 4px 8px;
      border-radius: 3px;
      font: inherit;
    }
    .send-row .id-input { width: 96px; }
    .send-row .data-input { flex: 1; min-width: 0; }
    .send-row button {
      background: var(--accent);
      color: var(--bg);
      border: none;
      font-weight: bold;
    }
    .send-row button:hover { background: #79c0ff; }
  `;

  @state() private entries: CANEntry[] = [];
  @state() private paused = false;
  @state() private autoscroll = true;
  @state() private hideStatus = false;
  @state() private hideTx = false;
  @state() private filter = "";

  private _idInput = "";
  private _dataInput = "";

  connectedCallback() {
    super.connectedCallback();
    onWsEvent("can_frame", (detail) => {
      if (this.paused) return;
      const entry = detail as CANEntry;
      const next = this.entries.length >= MAX_ENTRIES
        ? [...this.entries.slice(-(MAX_ENTRIES - 1)), entry]
        : [...this.entries, entry];
      this.entries = next;
    });
  }

  updated() {
    if (this.autoscroll && !this.paused) {
      const wrap = this.renderRoot.querySelector(".table-wrap") as HTMLElement;
      if (wrap) wrap.scrollTop = wrap.scrollHeight;
    }
  }

  private async _send() {
    const id = parseInt(this._idInput.trim(), 16);
    if (isNaN(id)) return;
    const dataStr = this._dataInput.trim();
    const data = dataStr ? dataStr.split(/\s+/).map((x) => parseInt(x, 16)) : [];
    if (data.some((b) => isNaN(b) || b < 0 || b > 0xff)) return;
    await sendFrame(id, data);
    this._idInput = "";
    this._dataInput = "";
    this.requestUpdate();
  }

  private _filtered(): CANEntry[] {
    let result = this.entries;
    if (this.hideStatus) {
      result = result.filter((e) => e.id !== PUNCHPRESS_STATUS_CAN_ID);
    }
    if (this.hideTx) {
      result = result.filter((e) => e.direction !== "tx");
    }
    const f = this.filter.trim().toLowerCase();
    if (f) {
      result = result.filter((e) => {
        const idHex = `0x${e.id.toString(16).padStart(3, "0")}`;
        return idHex.toLowerCase().includes(f) || e.direction.toLowerCase().includes(f);
      });
    }
    return result;
  }

  render() {
    const visible = this._filtered();
    return html`
      <h3>CAN Trace</h3>
      <div class="toolbar">
        <button
          class=${this.paused ? "active" : ""}
          @click=${() => (this.paused = !this.paused)}
        >${this.paused ? "▶ Resume" : "⏸ Pause"}</button>
        <button
          class=${this.autoscroll ? "active" : ""}
          @click=${() => (this.autoscroll = !this.autoscroll)}
        >Autoscroll</button>
        <button
          class=${this.hideStatus ? "active" : ""}
          @click=${() => (this.hideStatus = !this.hideStatus)}
        >Hide 0x200</button>
        <button
          class=${this.hideTx ? "active" : ""}
          @click=${() => (this.hideTx = !this.hideTx)}
        >Hide TX</button>
        <button @click=${() => (this.entries = [])}>Clear</button>
        <input
          placeholder="Filter (id or rx/tx)"
          .value=${this.filter}
          @input=${(e: Event) => (this.filter = (e.target as HTMLInputElement).value)}
        />
        <span class="stats">${visible.length} / ${this.entries.length}</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="dir">Dir</th>
              <th class="ts">Timestamp (FW)</th>
              <th class="id-col">ID</th>
              <th class="dlc">DLC</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            ${visible.map(
              (e) => html`
                <tr>
                  <td class="dir dir-${e.direction}">${e.direction.toUpperCase()}</td>
                  <td class="ts">${formatFwTimestamp(e.fw_timestamp_ms)}</td>
                  <td class="id-col">0x${e.id.toString(16).padStart(3, "0").toUpperCase()}</td>
                  <td class="dlc">${e.dlc}</td>
                  <td class="data">${e.data
                    .map((b) => b.toString(16).padStart(2, "0").toUpperCase())
                    .join(" ")}</td>
                </tr>
              `,
            )}
          </tbody>
        </table>
      </div>

      <div class="send-row">
        <input
          class="id-input"
          placeholder="ID (hex)"
          .value=${this._idInput}
          @input=${(e: Event) => (this._idInput = (e.target as HTMLInputElement).value)}
          @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") this._send(); }}
        />
        <input
          class="data-input"
          placeholder="Data bytes (hex, space-separated)"
          .value=${this._dataInput}
          @input=${(e: Event) => (this._dataInput = (e.target as HTMLInputElement).value)}
          @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") this._send(); }}
        />
        <button @click=${this._send}>Send</button>
      </div>
    `;
  }
}
