import { listDevices, type EspDeviceSummary } from "../api";

class DevicesStore {
  items = $state<EspDeviceSummary[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);

  async refresh() {
    this.loading = true;
    this.error = null;
    try {
      this.items = await listDevices();
    } catch (e) {
      this.error = String(e);
    } finally {
      this.loading = false;
    }
  }
}

export const devicesStore = new DevicesStore();
