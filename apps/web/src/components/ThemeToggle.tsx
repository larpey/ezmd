import { useEffect, useState } from "react";
import { THEME_KEY, readJson, writeJson } from "../lib/storage";

type Theme = "system" | "light" | "dark";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => readJson<Theme>(THEME_KEY, "system"));
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    writeJson(THEME_KEY, theme);
  }, [theme]);
  return (
    <label className="field-inline theme-toggle">
      <span>Theme</span>
      <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
