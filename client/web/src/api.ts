/**
 * REST client helpers for the discocan API.
 */

const BASE = "";

export async function sendFrame(id: number, data: number[]) {
  const r = await fetch(`${BASE}/api/can/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, data }),
  });
  return r.json();
}

export async function getThermoCurrentRest() {
  const r = await fetch(`${BASE}/api/thermo/current`);
  return r.json();
}

export async function getThermoMinMax() {
  const r = await fetch(`${BASE}/api/thermo/minmax`);
  return r.json();
}

export async function resetThermo() {
  const r = await fetch(`${BASE}/api/thermo/reset`, { method: "POST" });
  return r.json();
}

export async function sendThermoText(text: string) {
  const r = await fetch(`${BASE}/api/thermo/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function restartSim(
  x_mm: number | null = null,
  y_mm: number | null = null,
) {
  const r = await fetch(`${BASE}/api/punchpress/restart`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ x_mm, y_mm }),
  });
  return r.json();
}

export async function getPunchpressGeometry() {
  const r = await fetch(`${BASE}/api/punchpress/geometry`);
  return r.json();
}

export async function getPunchpressStatus() {
  const r = await fetch(`${BASE}/api/punchpress/status`);
  return r.json();
}

export async function getPunchpressPunches() {
  const r = await fetch(`${BASE}/api/punchpress/punches`);
  return r.json();
}

export async function setPunchpressAutoRun(active: boolean) {
  const r = await fetch(`${BASE}/api/punchpress/auto-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  return r.json();
}
