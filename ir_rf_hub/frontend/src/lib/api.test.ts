import { describe, expect, it } from "vitest";
import {
  devicesWithReceiver,
  devicesWithTransmitter,
  receiverFrequencyHz,
  type EspDeviceSummary,
} from "./api";

function device(overrides: Partial<EspDeviceSummary> & { id: string }): EspDeviceSummary {
  return {
    name: overrides.id,
    host: "10.0.0.1",
    port: 6053,
    tx_settle_ms: 150,
    rx_stop_settle_ms: 150,
    connect_timeout_s: 10,
    last_connected_at: null,
    last_error: null,
    connection_state: "idle",
    entities: [],
    ...overrides,
  };
}

const irReceiver = device({
  id: "ir-rx",
  entities: [{ esphome_key: 1, object_id: "ir_rx", domain: "infrared", role: "rx", frequency_hz: 38000 }],
});
const irTransmitter = device({
  id: "ir-tx",
  entities: [{ esphome_key: 2, object_id: "ir_tx", domain: "infrared", role: "tx", frequency_hz: null }],
});
const rfOnly = device({
  id: "rf-both",
  entities: [
    { esphome_key: 3, object_id: "rf_rx", domain: "radio_frequency", role: "rx", frequency_hz: 433920000 },
    { esphome_key: 4, object_id: "rf_tx", domain: "radio_frequency", role: "tx", frequency_hz: 433920000 },
  ],
});
const noEntities = device({ id: "bare" });

const devices = [irReceiver, irTransmitter, rfOnly, noEntities];

describe("devicesWithReceiver", () => {
  it("filters to devices with a receiver entity of the matching domain", () => {
    expect(devicesWithReceiver(devices, "ir").map((d) => d.id)).toEqual(["ir-rx"]);
    expect(devicesWithReceiver(devices, "rf").map((d) => d.id)).toEqual(["rf-both"]);
  });
});

describe("devicesWithTransmitter", () => {
  it("filters to devices with a transmitter entity of the matching domain", () => {
    expect(devicesWithTransmitter(devices, "ir").map((d) => d.id)).toEqual(["ir-tx"]);
    expect(devicesWithTransmitter(devices, "rf").map((d) => d.id)).toEqual(["rf-both"]);
  });
});

describe("receiverFrequencyHz", () => {
  it("returns the matching-domain receiver entity's carrier frequency", () => {
    expect(receiverFrequencyHz(devices, "ir-rx", "ir")).toBe(38000);
    expect(receiverFrequencyHz(devices, "rf-both", "rf")).toBe(433920000);
  });

  it("returns 0 when the device or a matching receiver entity isn't found", () => {
    expect(receiverFrequencyHz(devices, "does-not-exist", "ir")).toBe(0);
    // ir-tx has no rx entity at all.
    expect(receiverFrequencyHz(devices, "ir-tx", "ir")).toBe(0);
  });
});
