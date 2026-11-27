import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { storedMode } from "./components/ThemeSwitch";
import { applyPaletteVars, buildTheme, type ThemeMode } from "./theme";
import "./styles/tokens.css";

// before React mounts, so the first paint is already the right mode
applyPaletteVars(storedMode());

function Root() {
  const [mode, setMode] = useState<ThemeMode>(storedMode);
  // AntD derives hovers, borders and disabled states from its algorithm, so the
  // provider has to be rebuilt on a mode change rather than only the variables
  const onThemeChange = useCallback((next: ThemeMode) => setMode(next), []);
  return (
    <ConfigProvider locale={zhCN} theme={buildTheme(mode)}>
      <BrowserRouter>
        <App onThemeChange={onThemeChange} />
      </BrowserRouter>
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
