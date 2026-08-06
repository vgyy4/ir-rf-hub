export type ThemeMode = "auto" | "dark" | "light";

const MODE_KEY = "ir-rf-hub:theme-mode";
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

class ThemeStore {
  mode = $state<ThemeMode>(readStoredMode());
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

  private apply() {
    const dark = this.mode === "auto" ? (readHaDark() ?? this.mql.matches) : this.mode === "dark";
    this.dark = dark;
    document.documentElement.classList.toggle("dark", dark);
  }
}

export const themeStore = new ThemeStore();
