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
export function applyPaletteVars(root: HTMLElement = document.documentElement) {
  for (const [key, cssVar] of Object.entries(CSS_VAR)) {
    root.style.setProperty(cssVar, palette[key as keyof typeof palette]);
  }
}

const FONT_SANS =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

export const azuriteTheme: ThemeConfig = {
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
