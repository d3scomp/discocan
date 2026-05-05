import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { onWsEvent, wsState } from "../ws";

@customElement("connection-status")
export class ConnectionStatus extends LitElement {
  static styles = css`
    :host {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85rem;
      color: var(--text-dim);
    }
    .group {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .label { color: var(--text-dim); }
    .val { color: var(--text); }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot.connected,
    .dot.alive { background: var(--rx); box-shadow: 0 0 6px var(--rx); }
    .dot.disconnected,
    .dot.dead { background: var(--error); }
    .dot.reconnecting,
    .dot.connecting { background: var(--warn); animation: pulse 1.5s infinite; }
    .dot.unknown { background: var(--text-dim); }
    @keyframes pulse { 50% { opacity: 0.3; } }
    .sep { color: var(--border); }
  `;

  @state() private device = "unknown";
  @state() private ws = "connecting";

  connectedCallback() {
    super.connectedCallback();
    onWsEvent("connection_state", (d) => {
      this.device = d.state;
    });
    // poll WS state — there's no event for it, so we just check periodically
    setInterval(() => {
      this.ws = wsState();
    }, 500);
  }

  render() {
    return html`
      <span class="group">
        <span class="dot ${this.ws}"></span>
        <span class="label">ws:</span>
        <span class="val">${this.ws}</span>
      </span>
      <span class="sep">|</span>
      <span class="group">
        <span class="dot ${this.device}"></span>
        <span class="label">device:</span>
        <span class="val">${this.device}</span>
      </span>
    `;
  }
}
