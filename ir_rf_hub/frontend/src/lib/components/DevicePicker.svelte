<script lang="ts">
  import type { EspDeviceSummary } from "../api";
  import CheckIcon from "@lucide/svelte/icons/check";

  interface Props {
    devices: EspDeviceSummary[];
    selectedId: string | null;
    onSelect: (deviceId: string) => void;
  }

  let { devices, selectedId, onSelect }: Props = $props();

  const ONLINE_STATES = new Set(["idle", "rx_active", "tx_active", "rx_settling", "tx_settling"]);
</script>

{#if devices.length === 0}
  <p class="text-surface-500 text-sm italic">
    No matching ESPHome devices found. Add one with the "Devices" button first.
  </p>
{:else}
  <ul class="flex max-h-70 flex-col gap-2 overflow-y-auto">
    {#each devices as device (device.id)}
      <li>
        <button
          type="button"
          class={[
            "card w-full p-3 text-left transition-colors",
            device.id === selectedId
              ? "preset-tonal-primary border-primary-500 border"
              : "preset-filled-surface-100-900 hover:preset-tonal-surface border border-transparent",
          ].join(" ")}
          onclick={() => onSelect(device.id)}
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-medium">{device.name}</span>
            <div class="flex items-center gap-2">
              <span
                class={[
                  "text-xs tracking-wide uppercase",
                  ONLINE_STATES.has(device.connection_state) ? "text-success-500" : "text-surface-500",
                ].join(" ")}
              >
                {device.connection_state}
              </span>
              {#if device.id === selectedId}
                <CheckIcon class="text-primary-500 size-4" />
              {/if}
            </div>
          </div>
        </button>
      </li>
    {/each}
  </ul>
{/if}
