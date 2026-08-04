<script lang="ts">
  import type { EspDeviceSummary } from "../api";

  interface Props {
    devices: EspDeviceSummary[];
    selectedId: string | null;
    onSelect: (deviceId: string) => void;
  }

  let { devices, selectedId, onSelect }: Props = $props();
</script>

{#if devices.length === 0}
  <p class="empty">No matching ESPHome devices found. Add one in Settings first.</p>
{:else}
  <ul class="list">
    {#each devices as device (device.id)}
      <li>
        <button
          type="button"
          class="device"
          class:selected={device.id === selectedId}
          onclick={() => onSelect(device.id)}
        >
          <span class="name">{device.name}</span>
          <span class="status" class:online={device.connection_state === "idle" || device.connection_state === "rx_active" || device.connection_state === "tx_active"}>
            {device.connection_state}
          </span>
        </button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 280px;
    overflow-y: auto;
  }

  .device {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    border-radius: 10px;
    border: 1px solid #333944;
    background: #22262e;
    color: inherit;
    cursor: pointer;
    font-size: 0.95rem;
    text-align: left;
  }

  .device.selected {
    border-color: #58a6ff;
    background: #1e2b3d;
  }

  .status {
    font-size: 0.75rem;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .status.online {
    color: #3fb950;
  }

  .empty {
    color: #6b7280;
    font-style: italic;
  }

  @media (prefers-color-scheme: light) {
    .device {
      background: #f3f4f6;
      border-color: #d1d5db;
    }
    .device.selected {
      background: #e8f1ff;
    }
  }
</style>
