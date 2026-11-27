import { Segmented } from "antd";
import { useEffect, useState } from "react";

import { applyPaletteVars, type ThemeMode } from "../theme";

/**
 * Light, dark, or whatever the machine is set to.
 *
 * Three states rather than two because "follow the system" is the honest
 * default: a tool opened at a desk in the morning and again at night should
 * not need to be told twice, and someone who does want it pinned can say so.
 */

const STORAGE_KEY = "themeMode";

export function storedMode(): ThemeMode {
  const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

export default function ThemeSwitch({ onChange }: { onChange?: (mode: ThemeMode) => void }) {
  const [mode, setMode] = useState<ThemeMode>(storedMode);

  useEffect(() => {
    applyPaletteVars(mode);
    onChange?.(mode);
    if (mode !== "system") return;
    // while following the system, the page has to move when the system does
    const query = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const react = () => {
      applyPaletteVars("system");
      onChange?.("system");
    };
    query.addEventListener("change", react);
    return () => query.removeEventListener("change", react);
  }, [mode, onChange]);

  return (
    <Segmented
      size="small"
      value={mode}
      onChange={(next) => {
        const chosen = next as ThemeMode;
        globalThis.localStorage?.setItem(STORAGE_KEY, chosen);
        setMode(chosen);
      }}
      options={[
        { label: "跟随系统", value: "system" },
        { label: "浅色", value: "light" },
        { label: "深色", value: "dark" },
      ]}
    />
  );
}
