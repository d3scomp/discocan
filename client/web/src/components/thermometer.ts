import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import {
  getThermoCurrentRest,
  getThermoMinMax,
  resetThermo,
  sendThermoText,
} from "../api";
import { onWsEvent } from "../ws";

interface ThermoReading {
  time: number;
  temp: number;
  humidity: number;
}

@customElement("thermometer-widget")
export class ThermometerWidget extends LitElement {
  static styles = css`
    :host {
      display: block;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.6rem;
      font-family: ui-monospace, "SF Mono", Consolas, Menlo, monospace;
      font-size: 0.85rem;
    }
    h3 {
      color: var(--warn);
      margin-bottom: 0.5rem;
      font-size: 0.95rem;
      padding: 0 6px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px 12px;
      padding: 0.2rem 6px;
    }
    .label { color: var(--text-dim); }
    .val { color: var(--text); text-align: right; font-feature-settings: "tnum"; }
    .chart-wrap {
      margin: 0.5rem 0;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 3px;
      padding: 4px;
    }
    svg {
      display: block;
      width: 100%;
      height: 90px;
    }

    .controls {
      margin-top: 0.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }
    textarea {
      background: var(--bg-input);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 4px 6px;
      border-radius: 3px;
      font: inherit;
      resize: vertical;
      min-height: 44px;
    }
    .btn-row {
      display: flex;
      gap: 0.4rem;
    }
    .btn-row button {
      flex: 1;
      padding: 5px 12px;
      border-radius: 3px;
      cursor: pointer;
      font: inherit;
      border: none;
      color: white;
    }
    .btn-send { background: #2d6a9f; }
    .btn-send:hover { background: #3a84c4; }
    .btn-reset { background: #9f5a2d; }
    .btn-reset:hover { background: #b86b35; }
  `;

  @state() private temp: number | null = null;
  @state() private humidity: number | null = null;
  @state() private minTemp: number | null = null;
  @state() private maxTemp: number | null = null;
  @state() private minHum: number | null = null;
  @state() private maxHum: number | null = null;
  @state() private history: ThermoReading[] = [];

  private _textInput = "";

  connectedCallback() {
    super.connectedCallback();
    onWsEvent("thermo_current", (d) => {
      this.temp = d.temp;
      this.humidity = d.humidity;
      this.history = [
        ...this.history.slice(-119),
        { time: Date.now(), temp: d.temp, humidity: d.humidity },
      ];
    });
    onWsEvent("thermo_minmax", (d) => {
      this.minTemp = d.min_temp;
      this.maxTemp = d.max_temp;
      this.minHum = d.min_hum;
      this.maxHum = d.max_hum;
    });
    // Pre-populate from REST so refreshing the page shows current values immediately.
    getThermoCurrentRest()
      .then((d) => {
        if (d?.temp != null) this.temp = d.temp;
        if (d?.humidity != null) this.humidity = d.humidity;
      })
      .catch(() => {});
    getThermoMinMax()
      .then((d) => {
        this.minTemp = d?.min_temp ?? null;
        this.maxTemp = d?.max_temp ?? null;
        this.minHum = d?.min_hum ?? null;
        this.maxHum = d?.max_hum ?? null;
      })
      .catch(() => {});
  }

  private _renderChart() {
    if (this.history.length < 2) {
      return html`<div class="chart-wrap"><svg></svg></div>`;
    }
    const w = 320;
    const h = 90;
    const temps = this.history.map((r) => r.temp);
    const hums = this.history.map((r) => r.humidity);
    const tMin = Math.min(...temps);
    const tMax = Math.max(...temps);
    const hMin = Math.min(...hums);
    const hMax = Math.max(...hums);
    const tRange = tMax - tMin || 1;
    const hRange = hMax - hMin || 1;

    const tPts = this.history
      .map((r, i) => {
        const x = (i / (this.history.length - 1)) * w;
        const y = h - ((r.temp - tMin) / tRange) * (h - 6) - 3;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    const hPts = this.history
      .map((r, i) => {
        const x = (i / (this.history.length - 1)) * w;
        const y = h - ((r.humidity - hMin) / hRange) * (h - 6) - 3;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    return html`
      <div class="chart-wrap">
        <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
          <polyline points="${hPts}" fill="none" stroke="#5fb0d8" stroke-width="1" opacity="0.7"/>
          <polyline points="${tPts}" fill="none" stroke="var(--warn)" stroke-width="1.5"/>
        </svg>
      </div>
    `;
  }

  private async _reset() {
    await resetThermo();
  }

  private async _sendText() {
    if (this._textInput.trim()) {
      await sendThermoText(this._textInput);
      this._textInput = "";
      this.requestUpdate();
    }
  }

  render() {
    const fmt = (v: number | null) => (v === null ? "—" : v.toFixed(1));
    return html`
      <h3>Thermometer</h3>
      <div class="grid">
        <span class="label">Temperature</span>
        <span class="val">${fmt(this.temp)} °C</span>
        <span class="label">Humidity</span>
        <span class="val">${fmt(this.humidity)} %</span>
        <span class="label">Min / Max T</span>
        <span class="val">${fmt(this.minTemp)} / ${fmt(this.maxTemp)} °C</span>
        <span class="label">Min / Max H</span>
        <span class="val">${fmt(this.minHum)} / ${fmt(this.maxHum)} %</span>
      </div>
      ${this._renderChart()}
      <div class="controls">
        <textarea
          rows="2"
          placeholder="Text to display (\\n for newline)"
          .value=${this._textInput}
          @input=${(e: Event) => (this._textInput = (e.target as HTMLTextAreaElement).value)}
        ></textarea>
        <div class="btn-row">
          <button class="btn-send" @click=${this._sendText}>Send Text</button>
          <button class="btn-reset" @click=${this._reset}>Reset Min/Max</button>
        </div>
      </div>
    `;
  }
}
