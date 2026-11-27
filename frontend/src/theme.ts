import { theme as antdTheme } from "antd";
import type { ThemeConfig } from "antd";

/**
 * Azurite palette, mirrored from styles/tokens.css.
 *
 * Duplicated as TS constants because AntD's theme is consumed in JS, not CSS —
 * the two lists must be changed together. Components should prefer the CSS
 * custom properties; these exist so AntD's own derived tokens (hovers, borders,
 * disabled states) are generated from the same palette instead of its default
 * blue.
 */
export const palette = {
  ground: "#F7F9FA",
  surface: "#FFFFFF",
  sunk: "#EEF2F5",
  line: "#DCE3E8",
  lineStrong: "#BCC7CF",

  ink: "#141A1F",
  inkSoft: "#4A555E",
  inkFaint: "#7A858D",

  azurite: "#17568F",
  azuriteWeak: "#E3EDF6",

  up: "#077256",
  down: "#C8323F",
  ochre: "#9A6508",
  gossan: "#8E3A1C",

  measured: "#141A1F",
  indicated: "#4A555E",
  inferred: "#6E787F",
  absent: "#C2CBD1",
} as const;

/**
 * The same palette after dark, with the same four jobs.
 *
 * Not an inversion: pure black gives the hues nowhere to sit, so the ground is
 * a very dark slate from the same family as the light one. Every accent was
 * re-picked rather than lightened, because the light hues fall under 4.5:1 on
 * a dark ground. Measured against #161D24 and #0E1419, the lowest contrast
 * here is 4.87:1 (inkFaint) and the rest clear 5:1, so every one of these
 * carries body text at WCAG AA.
 *
 * The keys mirror the light palette exactly. A missing key would leave its
 * custom property at the previous mode's value, which shows up as one stray
 * light-mode colour rather than as an obvious failure.
 */
export const darkPalette: Record<keyof typeof palette, string> = {
  ground: "#0E1419",
  surface: "#161D24",
  sunk: "#1E262E",
  line: "#2C3640",
  lineStrong: "#415059",

  ink: "#E6ECF1",
  inkSoft: "#A8B4BE",
  inkFaint: "#7E8B95",

  azurite: "#6FA8DC",
  azuriteWeak: "#1B2D3F",

  up: "#3FBF92",
  down: "#F2727F",
  ochre: "#D9A441",
  gossan: "#D4784F",

  measured: "#E6ECF1",
  indicated: "#A8B4BE",
  inferred: "#8A959E",
  absent: "#3A454E",
} as const;

export type ThemeMode = "system" | "light" | "dark";

/** What `system` currently resolves to. */
export function resolveMode(mode: ThemeMode): "light" | "dark" {
  if (mode !== "system") return mode;
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** CSS custom property name for each palette entry. */
const CSS_VAR: Record<keyof typeof palette, string> = {
  ground: "--ground",
  surface: "--surface",
  sunk: "--sunk",
  line: "--line",
  lineStrong: "--line-strong",
  ink: "--ink",
  inkSoft: "--ink-soft",
  inkFaint: "--ink-faint",
  azurite: "--azurite",
  azuriteWeak: "--azurite-weak",
  up: "--up",
  down: "--down",
  ochre: "--ochre",
  gossan: "--gossan",
  measured: "--c-measured",
  indicated: "--c-indicated",
  inferred: "--c-inferred",
  absent: "--c-absent",
};

/**
 * Publish the palette as CSS custom properties.
 *
 * The palette lives here, in one place, because AntD's theme is consumed in JS.
 * Components read it as `var(--azurite)`; writing those values from the same
 * constants means the stylesheet and the component library can never drift into
 * disagreeing about what the accent colour is. tokens.css still ships the same
 * values as literals so the first paint is correct before React mounts.
 */
export function applyPaletteVars(
  mode: ThemeMode = "light",
  root: HTMLElement = document.documentElement,
) {
  const resolved = resolveMode(mode);
  const active: Record<string, string> = resolved === "dark" ? darkPalette : palette;
  for (const [key, cssVar] of Object.entries(CSS_VAR)) {
    root.style.setProperty(cssVar, active[key]);
  }
  // stamped so a stylesheet can react too, and so the resolved mode is
  // inspectable rather than inferred from a colour
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
}

const FONT_SANS =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

/**
 * Build the AntD theme for one mode.
 *
 * AntD derives hovers, borders and disabled states from its own algorithm, so
 * the dark palette has to reach it through that rather than through CSS alone
 * — overriding the variables without switching the algorithm leaves every
 * derived token computed against a white ground.
 */
export function buildTheme(mode: ThemeMode = "light"): ThemeConfig {
  const resolved = resolveMode(mode);
  const p = resolved === "dark" ? darkPalette : palette;
  return {
    algorithm: resolved === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    ...tokensFor(p),
  };
}

function tokensFor(palette: Record<keyof typeof import('./theme').palette, string>): ThemeConfig {
  return {
  token: {
    colorPrimary: palette.azurite,
    colorInfo: palette.azurite,
    // success/error are AntD's semantic pair; here they mean price direction
    // and nothing else. Risk states use ochre/gossan directly, so that a red
    // pill never has to be read as either "down" or "dangerous".
    colorSuccess: palette.up,
    colorError: palette.down,
    colorWarning: palette.ochre,

    colorTextBase: palette.ink,
    colorBgBase: palette.surface,
    colorBgLayout: palette.ground,
    colorBorder: palette.line,
    colorBorderSecondary: palette.sunk,

    fontFamily: FONT_SANS,
    fontSize: 14,

    // 6 read as generically rounded; 3 keeps panels looking like instruments
    // rather than cards, which suits a tool that is scanned rather than browsed.
    borderRadius: 3,
    wireframe: false,
  },
  components: {
    Layout: {
      siderBg: palette.sunk,
      bodyBg: palette.ground,
      headerBg: palette.surface,
      footerBg: palette.ground,
    },
    Menu: {
      itemBg: palette.sunk,
      subMenuItemBg: palette.sunk,
      itemSelectedBg: palette.azuriteWeak,
      itemSelectedColor: palette.azurite,
      itemColor: palette.inkSoft,
      itemHoverBg: palette.azuriteWeak,
      itemBorderRadius: 0,
      itemMarginInline: 0,
      itemMarginBlock: 0,
      groupTitleColor: palette.inkFaint,
      groupTitleFontSize: 11,
    },
    Table: {
      headerBg: palette.sunk,
      headerColor: palette.inkFaint,
      headerSplitColor: palette.line,
      borderColor: palette.line,
      rowHoverBg: palette.azuriteWeak,
      cellPaddingBlockSM: 8,
    },
    Card: {
      headerBg: palette.surface,
      colorBorderSecondary: palette.line,
    },
    Tag: {
      defaultBg: palette.sunk,
      defaultColor: palette.inkSoft,
    },
    Descriptions: {
      labelBg: palette.sunk,
      colorSplit: palette.line,
    },
    Alert: {
      colorInfoBg: palette.azuriteWeak,
      colorInfoBorder: palette.line,
    },
    Statistic: {
      contentFontSize: 26,
    },
    Progress: {
      defaultColor: palette.azurite,
      remainingColor: palette.sunk,
    },
    Empty: {
      colorTextDescription: palette.inkFaint,
    },
  },
};
}

/** The light theme, kept under its original name for existing callers. */
export const azuriteTheme: ThemeConfig = buildTheme("light");
