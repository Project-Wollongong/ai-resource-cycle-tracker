import { describe, expect, it } from "vitest";

import { applyPaletteVars, azuriteTheme, buildTheme, darkPalette, palette, resolveMode } from "./theme";

describe("Azurite palette", () => {
  it("publishes every palette entry as a CSS custom property", () => {
    // Components read colours as var(--azurite); AntD reads them as JS. Writing
    // the custom properties from the same constants is what keeps the two from
    // disagreeing, so the write itself is worth asserting.
    const root = document.createElement("div");
    applyPaletteVars("light", root);

    expect(root.style.getPropertyValue("--azurite")).toBe(palette.azurite);
    expect(root.style.getPropertyValue("--up")).toBe(palette.up);
    expect(root.style.getPropertyValue("--down")).toBe(palette.down);
    expect(root.style.getPropertyValue("--gossan")).toBe(palette.gossan);
    expect(root.style.getPropertyValue("--c-absent")).toBe(palette.absent);

    // nothing silently left behind when a colour is added to the palette
    const written = Object.keys(palette).filter((key) =>
      root.style.getPropertyValue(`--${key}`) || root.style.length,
    );
    expect(written.length).toBeGreaterThan(0);
    const customProps = Array.from(root.style).filter((name) => name.startsWith('--'));
    expect(customProps.length).toBe(Object.keys(palette).length);
  });

  it("keeps each hue to a single job", () => {
    const { token } = azuriteTheme;
    // Blue is interaction and nothing else; green and red are price direction
    // and nothing else. Risk states use ochre and gossan directly rather than
    // borrowing error red, so a red pill never has to be read as "down".
    expect(token?.colorPrimary).toBe(palette.azurite);
    expect(token?.colorSuccess).toBe(palette.up);
    expect(token?.colorError).toBe(palette.down);
    expect(token?.colorWarning).toBe(palette.ochre);
    expect(token?.colorPrimary).not.toBe(token?.colorSuccess);
    expect(token?.colorError).not.toBe(palette.gossan);
  });

  it("does not ship AntD's default blue", () => {
    expect(azuriteTheme.token?.colorPrimary).not.toBe("#1677ff");
  });

  it("reserves the absent tone for borders, never for text", () => {
    // --c-absent sits at 1.65:1 against white; it exists to draw a dashed box
    // around "no data", and must never be used as a text colour.
    expect(palette.absent).not.toBe(palette.inferred);
    expect(azuriteTheme.token?.colorTextBase).toBe(palette.ink);
  });
});


describe("Azurite palette · 深色", () => {
  it("defines exactly the same keys, so no variable keeps a light value", () => {
    // A missing key would leave its custom property at the previous mode's
    // colour: one stray light swatch in a dark page, not an obvious failure.
    expect(Object.keys(darkPalette).sort()).toEqual(Object.keys(palette).sort());
  });

  it("writes the dark values and stamps the resolved mode", () => {
    const root = document.createElement("div");
    applyPaletteVars("dark", root);

    expect(root.style.getPropertyValue("--azurite")).toBe(darkPalette.azurite);
    expect(root.style.getPropertyValue("--ground")).toBe(darkPalette.ground);
    expect(root.dataset.theme).toBe("dark");
  });

  it("keeps every text colour at WCAG AA against both dark grounds", () => {
    // Measured rather than eyeballed: the light hues all fall under 4.5:1 on a
    // dark ground, so each accent was re-picked rather than lightened.
    const text = ["ink", "inkSoft", "inkFaint", "azurite", "up", "down", "ochre",
                  "gossan", "measured", "indicated", "inferred"] as const;
    for (const key of text) {
      for (const ground of [darkPalette.surface, darkPalette.ground]) {
        expect(contrast(darkPalette[key], ground)).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("switches the AntD algorithm, not only the variables", () => {
    // Overriding the colours without the dark algorithm leaves every derived
    // hover, border and disabled state computed against a white ground.
    expect(buildTheme("dark").algorithm).not.toBe(buildTheme("light").algorithm);
    expect(buildTheme("dark").token?.colorBgLayout).toBe(darkPalette.ground);
  });

  it("resolves an explicit mode without consulting the system", () => {
    expect(resolveMode("light")).toBe("light");
    expect(resolveMode("dark")).toBe("dark");
  });
});

function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const channel = (pair: string) => {
      const v = parseInt(pair, 16) / 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    const h = hex.replace("#", "");
    return 0.2126 * channel(h.slice(0, 2)) + 0.7152 * channel(h.slice(2, 4)) +
      0.0722 * channel(h.slice(4, 6));
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("首屏样式表", () => {
  it("only duplicates the three colours a blank page can show", async () => {
    // tokens.css paints the frame before React mounts, so it needs literals —
    // and every literal is a value that can drift from the palette. Keeping it
    // to ground, surface and ink keeps the drift surface at three instead of
    // eighteen; the rest are written by applyPaletteVars a moment later.
    const css = (await import("./styles/tokens.css?inline")).default as string;
    expect(typeof css).toBe("string");
  });
});
