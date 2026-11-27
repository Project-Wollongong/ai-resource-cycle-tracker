import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ThemeSwitch, { storedMode } from "./ThemeSwitch";
import { darkPalette, palette } from "../theme";

beforeEach(() => {
  globalThis.localStorage?.clear();
  document.documentElement.removeAttribute("style");
  document.documentElement.removeAttribute("data-theme");
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

describe("ThemeSwitch", () => {
  it("follows the system until told otherwise", () => {
    // Opened at a desk in the morning and again at night, a tool should not
    // need to be told twice.
    expect(storedMode()).toBe("system");
  });

  it("writes the dark palette onto the root when dark is chosen", () => {
    render(<ThemeSwitch />);
    fireEvent.click(screen.getByText("深色"));

    expect(document.documentElement.style.getPropertyValue("--ground")).toBe(darkPalette.ground);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("remembers the choice across a reload", () => {
    render(<ThemeSwitch />);
    fireEvent.click(screen.getByText("深色"));

    expect(storedMode()).toBe("dark");
  });

  it("an explicit light choice is not overridden by a dark machine", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true, media: query, addEventListener: () => {}, removeEventListener: () => {},
    }));
    render(<ThemeSwitch />);
    fireEvent.click(screen.getByText("浅色"));

    expect(document.documentElement.style.getPropertyValue("--ground")).toBe(palette.ground);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("tells the host which mode is active, so AntD can be rebuilt", () => {
    // Switching the variables without switching the algorithm leaves every
    // derived hover and border computed against a white ground.
    const onChange = vi.fn();
    render(<ThemeSwitch onChange={onChange} />);
    fireEvent.click(screen.getByText("深色"));

    expect(onChange).toHaveBeenCalledWith("dark");
  });
});
