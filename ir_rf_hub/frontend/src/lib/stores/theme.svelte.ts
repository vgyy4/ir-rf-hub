export type ThemeMode = "auto" | "dark" | "light";
export type Palette = "seaglass" | "meadow" | "sorbet" | "catppuccin";

/** Palette is independent of light/dark -- every palette defines both schemes,
 * so the two settings compose rather than override each other. `catppuccin` is
 * the pre-shadcn theme, kept for anyone who preferred it. */
export const PALETTES: { id: Palette; label: string }[] = [
  { id: "seaglass", label: "Seaglass" },
  { id: "meadow", label: "Meadow" },
  { id: "sorbet", label: "Sorbet" },
  { id: "catppuccin", label: "Catppuccin" },
];

const MODE_KEY = "ir-rf-hub:theme-mode";
const PALETTE_KEY = "ir-rf-hub:palette";
/** Home Assistant's own theme-picker preference. Ingress add-ons are served
 * from the same origin as the HA frontend, so this localStorage key is the
 * literal one HA writes to (see home-assistant/frontend's ha-pref-storage.ts).
 * `dark` is omitted when the user's HA theme is itself set to "Auto". */
const HA_THEME_KEY = "selectedTheme";

function readHaDark(): boolean | null {
  try {
    const raw = window.localStorage.getItem(HA_THEME_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { dark?: boolean };
    return typeof parsed.dark === "boolean" ? parsed.dark : null;
  } catch {
    return null;
  }
}

function readStoredMode(): ThemeMode {
  const raw = window.localStorage.getItem(MODE_KEY);
  return raw === "dark" || raw === "light" || raw === "auto" ? raw : "auto";
}

function readStoredPalette(): Palette {
  const raw = window.localStorage.getItem(PALETTE_KEY);
  return PALETTES.some((p) => p.id === raw) ? (raw as Palette) : "seaglass";
}

class ThemeStore {
  mode = $state<ThemeMode>(readStoredMode());
  palette = $state<Palette>(readStoredPalette());
  dark = $state(false);

  private mql = window.matchMedia("(prefers-color-scheme: dark)");

  constructor() {
    this.apply();
    this.mql.addEventListener("change", () => this.apply());
    window.addEventListener("storage", (e) => {
      if (e.key === HA_THEME_KEY) this.apply();
    });
  }

  setMode(mode: ThemeMode) {
    this.mode = mode;
    window.localStorage.setItem(MODE_KEY, mode);
    this.apply();
  }

  setPalette(palette: Palette) {
    this.palette = palette;
    window.localStorage.setItem(PALETTE_KEY, palette);
    this.apply();
  }

  private apply() {
    const dark = this.mode === "auto" ? (readHaDark() ?? this.mql.matches) : this.mode === "dark";
    this.dark = dark;
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.dataset.theme = this.palette;
  }
}

export const themeStore = new ThemeStore();
