/**
 * dark-mode.js
 * ---------------------------------------------------------------------
 * Toggles the dashboard's color theme between light and dark by setting
 * `data-theme` on the <html> element, persisted in localStorage and
 * initialized before first paint to avoid a flash of the wrong theme.
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  const STORAGE_KEY = "indusmind.theme";

  function getPreferredTheme() {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
  }

  // Apply immediately (not waiting for DOMContentLoaded) to prevent
  // a flash of the incorrect theme on page load.
  applyTheme(getPreferredTheme());

  function initToggle() {
    const toggleButton = document.querySelector("[data-theme-toggle]");
    if (!toggleButton) return;

    toggleButton.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      window.localStorage.setItem(STORAGE_KEY, next);
    });
  }

  document.addEventListener("DOMContentLoaded", initToggle);
})();
