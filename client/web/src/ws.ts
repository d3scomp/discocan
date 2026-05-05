/**
 * Singleton WebSocket connection with EventTarget-based dispatch.
 */

const wsEvents = new EventTarget();

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _state: "connecting" | "alive" | "dead" = "connecting";

function connect() {
  _state = "connecting";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    _state = "alive";
  };

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      wsEvents.dispatchEvent(
        Object.assign(new Event(data.type ?? "unknown"), { detail: data }),
      );
    } catch {
      // ignore malformed messages
    }
  };

  ws.onclose = () => {
    _state = "dead";
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  };

  ws.onerror = () => {
    // close handler will run; just mark dead now so the UI updates promptly
    _state = "dead";
  };
}

connect();

export function onWsEvent(type: string, cb: (detail: any) => void) {
  wsEvents.addEventListener(type, (e: any) => cb(e.detail));
}

export function wsState(): "connecting" | "alive" | "dead" {
  return _state;
}
