// Deliberately relative (no leading slash): under HA Ingress this app is
// served from a dynamic per-session path (/api/hassio_ingress/<token>/),
// so a request to "/api/health" would hit the Home Assistant frontend's
// own root instead of being proxied to this App. A relative "api/health"
// resolves against the current document's path in both contexts -- plain
// http://host:8099/ in local dev, and the ingress-prefixed path in
// production -- and the dev server proxy in vite.config.ts forwards it to
// the backend on :8099 either way.
const API_BASE = "api/";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail ?? message;
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("health");
}

export type SignalType = "ir" | "rf";

export interface DeviceEntitySummary {
  esphome_key: number;
  object_id: string;
  domain: "infrared" | "radio_frequency";
  role: "tx" | "rx";
  frequency_hz: number | null;
}

export interface EspDeviceSummary {
  id: string;
  name: string;
  host: string;
  port: number;
  tx_settle_ms: number;
  rx_stop_settle_ms: number;
  connect_timeout_s: number;
  last_connected_at: string | null;
  last_error: string | null;
  connection_state: string;
  entities: DeviceEntitySummary[];
}

export function listDevices(): Promise<EspDeviceSummary[]> {
  return request<EspDeviceSummary[]>("devices");
}

const domainForType = (type: SignalType) => (type === "ir" ? "infrared" : "radio_frequency");

export function devicesWithReceiver(devices: EspDeviceSummary[], type: SignalType): EspDeviceSummary[] {
  const domain = domainForType(type);
  return devices.filter((d) => d.entities.some((e) => e.domain === domain && e.role === "rx"));
}

export function devicesWithTransmitter(devices: EspDeviceSummary[], type: SignalType): EspDeviceSummary[] {
  const domain = domainForType(type);
  return devices.filter((d) => d.entities.some((e) => e.domain === domain && e.role === "tx"));
}

export interface RecordingSessionResponse {
  session_id: string;
  device_id: string;
  type: SignalType;
}

export interface RecordingStopResponse {
  session_id: string;
  capture_count: number;
  timings: number[];
}

export function startRecording(type: SignalType, deviceId: string): Promise<RecordingSessionResponse> {
  return request<RecordingSessionResponse>("recording/sessions", {
    method: "POST",
    body: JSON.stringify({ type, device_id: deviceId }),
  });
}

export function clearRecording(sessionId: string): Promise<void> {
  return request<void>(`recording/sessions/${sessionId}/clear`, { method: "POST" });
}

export function stopRecording(sessionId: string): Promise<RecordingStopResponse> {
  return request<RecordingStopResponse>(`recording/sessions/${sessionId}/stop`, { method: "POST" });
}

export function discardRecording(sessionId: string): Promise<void> {
  return request<void>(`recording/sessions/${sessionId}/discard`, { method: "POST" });
}

export interface CommandSummary {
  id: string;
  name: string;
  type: SignalType;
  default_device_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CommandDetail extends CommandSummary {
  raw_timings: number[];
  carrier_frequency_hz: number;
  repeat_count: number;
}

export function listCommands(): Promise<CommandSummary[]> {
  return request<CommandSummary[]>("commands");
}

export function getCommand(id: string): Promise<CommandDetail> {
  return request<CommandDetail>(`commands/${id}`);
}

export interface CreateCommandRequest {
  name: string;
  type: SignalType;
  raw_timings: number[];
  carrier_frequency_hz: number;
  default_device_id?: string | null;
  recorded_from_device_id?: string | null;
}

export function createCommand(payload: CreateCommandRequest): Promise<CommandDetail> {
  return request<CommandDetail>("commands", { method: "POST", body: JSON.stringify(payload) });
}

export function updateCommand(id: string, payload: Partial<CreateCommandRequest>): Promise<CommandDetail> {
  return request<CommandDetail>(`commands/${id}`, { method: "PUT", body: JSON.stringify(payload) });
}

export function deleteCommand(id: string): Promise<void> {
  return request<void>(`commands/${id}`, { method: "DELETE" });
}

export function fireCommand(id: string, deviceId?: string): Promise<void> {
  return request<void>(`commands/${id}/fire`, {
    method: "POST",
    body: JSON.stringify(deviceId ? { device_id: deviceId } : {}),
  });
}

export function candidateDevicesForCommand(id: string): Promise<EspDeviceSummary[]> {
  return request<EspDeviceSummary[]>(`commands/${id}/candidate-devices`);
}
