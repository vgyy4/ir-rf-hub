import { connectEventSocket } from "../ws";
import { listCommands, type CommandSummary } from "../api";

class CommandsStore {
  items = $state<CommandSummary[]>([]);
  loading = $state(false);
  error = $state<string | null>(null);
  private disconnect: (() => void) | null = null;

  async refresh() {
    this.loading = true;
    this.error = null;
    try {
      this.items = await listCommands();
    } catch (e) {
      this.error = String(e);
    } finally {
      this.loading = false;
    }
  }

  /** Subscribe to the general event bus so every open tab stays in sync as
   * commands are created/renamed/deleted -- REST resync as the correctness
   * backstop, WS as the fast path (same pattern the companion integration
   * will use in Phase 5).
   */
  startLiveSync() {
    if (this.disconnect) return;
    this.disconnect = connectEventSocket(
      (event) => {
        if (event.type === "command.created" || event.type === "command.updated" || event.type === "command.deleted") {
          void this.refresh();
        }
      },
      // The socket itself now reconnects on its own (see ws.ts), but a
      // reconnect means some events could have been missed while it was
      // down -- a full resync is the correctness backstop for that gap.
      () => void this.refresh(),
    );
  }

  stopLiveSync() {
    this.disconnect?.();
    this.disconnect = null;
  }
}

export const commandsStore = new CommandsStore();
