import { describe, expect, it } from "vitest";

import { applyPaletteVars, azuriteTheme, palette } from "./theme";

describe("Azurite palette", () => {
  it("publishes every palette entry as a CSS custom property", () => {
    // Components read colours as var(--azurite); AntD reads them as JS. Writing
    // the custom properties from the same constants is what keeps the two from
    // disagreeing, so the write itself is worth asserting.
    const root = document.createElement("div");
    applyPaletteVars(root);

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
    expect(root.style.length).toBe(Object.keys(palette).length);
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
