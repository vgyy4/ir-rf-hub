<script lang="ts">
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu/index.js";
  import { Button } from "$lib/components/ui/button/index.js";
  import { themeStore, PALETTES, type ThemeMode, type Palette } from "../stores/theme.svelte";
  import { haptics } from "../haptics";
  import PaletteIcon from "@lucide/svelte/icons/palette";
  import SunIcon from "@lucide/svelte/icons/sun";
  import MoonIcon from "@lucide/svelte/icons/moon";
  import MonitorIcon from "@lucide/svelte/icons/monitor-smartphone";

  // Swatches can't read the palette's own CSS variables -- those only resolve
  // for whichever palette is currently active, so every row would render in
  // the same colours. These are literals: each palette's brand / IR / RF hue
  // in the form that reads well against both a light and a dark popover.
  const SWATCHES: Record<Palette, [string, string, string]> = {
    seaglass: ["#9BD2CD", "#FCCE7C", "#2C7A78"],
    meadow: ["#D4A373", "#CCD5AE", "#9C5F33"],
    sorbet: ["#C7CEFF", "#FFB4A2", "#A8E6CF"],
    catppuccin: ["#B4BEFE", "#F5C2E7", "#94E2D5"],
  };

  const MODES: { id: ThemeMode; label: string; icon: typeof SunIcon }[] = [
    { id: "auto", label: "Auto (HA)", icon: MonitorIcon },
    { id: "dark", label: "Dark", icon: MoonIcon },
    { id: "light", label: "Light", icon: SunIcon },
  ];

  function pickPalette(value: string) {
    haptics.tap();
    themeStore.setPalette(value as Palette);
  }

  function pickMode(value: string) {
    haptics.tap();
    themeStore.setMode(value as ThemeMode);
  }
</script>

<DropdownMenu.Root>
  <DropdownMenu.Trigger>
    {#snippet child({ props })}
      <Button {...props} variant="ghost" size="icon" aria-label="Theme and colour scheme">
        <PaletteIcon />
      </Button>
    {/snippet}
  </DropdownMenu.Trigger>

  <DropdownMenu.Content align="end" class="w-52">
    <DropdownMenu.Label class="text-muted-foreground text-xs tracking-wide uppercase">
      Palette
    </DropdownMenu.Label>
    <DropdownMenu.RadioGroup value={themeStore.palette} onValueChange={pickPalette}>
      {#each PALETTES as palette (palette.id)}
        <DropdownMenu.RadioItem value={palette.id}>
          <span class="flex items-center gap-2">
            <span class="flex" aria-hidden="true">
              {#each SWATCHES[palette.id] as swatch, i (i)}
                <span
                  class="border-popover size-3 rounded-full border-2 not-first:-ml-1"
                  style="background-color: {swatch}"
                ></span>
              {/each}
            </span>
            {palette.label}
          </span>
        </DropdownMenu.RadioItem>
      {/each}
    </DropdownMenu.RadioGroup>

    <DropdownMenu.Separator />

    <DropdownMenu.Label class="text-muted-foreground text-xs tracking-wide uppercase">
      Mode
    </DropdownMenu.Label>
    <DropdownMenu.RadioGroup value={themeStore.mode} onValueChange={pickMode}>
      {#each MODES as mode (mode.id)}
        <DropdownMenu.RadioItem value={mode.id}>
          <span class="flex items-center gap-2">
            <mode.icon class="text-muted-foreground size-3.5" />
            {mode.label}
          </span>
        </DropdownMenu.RadioItem>
      {/each}
    </DropdownMenu.RadioGroup>
  </DropdownMenu.Content>
</DropdownMenu.Root>
