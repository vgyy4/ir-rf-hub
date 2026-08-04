<script lang="ts">
  import type { CommandSummary } from "../api";

  interface Props {
    command: CommandSummary;
    onFire: (command: CommandSummary) => void;
    onEdit: (command: CommandSummary) => void;
  }

  let { command, onFire, onEdit }: Props = $props();
</script>

<li class="row">
  <button type="button" class="fire" onclick={() => onFire(command)}>
    <span class="badge" class:rf={command.type === "rf"}>{command.type.toUpperCase()}</span>
    <span class="name">{command.name}</span>
  </button>
  <button type="button" class="edit" aria-label="Edit {command.name}" onclick={() => onEdit(command)}>
    ✏️
  </button>
</li>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 10px;
    background: #22262e;
    border: 1px solid #333944;
  }

  .fire {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.85rem 1rem;
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    font-size: 1rem;
    text-align: left;
  }

  .badge {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.15rem 0.45rem;
    border-radius: 5px;
    background: #1f3a5f;
    color: #79c0ff;
  }

  .badge.rf {
    background: #3a1f5f;
    color: #d2a8ff;
  }

  .edit {
    background: transparent;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    padding: 0.85rem;
    opacity: 0.7;
  }

  .edit:hover {
    opacity: 1;
  }

  @media (prefers-color-scheme: light) {
    .row {
      background: #f3f4f6;
      border-color: #d1d5db;
    }
  }
</style>
