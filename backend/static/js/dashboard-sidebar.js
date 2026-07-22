/**
 * dashboard-sidebar.js
 * ---------------------------------------------------------------------
 * Controls the collapsible left sidebar (desktop collapse/expand,
 * persisted in localStorage) and the off-canvas mobile drawer.
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  const STORAGE_KEY = "indusmind.sidebar.collapsed";

  function applyCollapsedState(root, collapsed) {
    root.setAttribute("data-sidebar-collapsed", String(collapsed));
  }

  function initCollapseToggle() {
    const root = document.documentElement;
    const toggleButton = document.querySelector("[data-sidebar-collapse-toggle]");
    if (!toggleButton) return;

    const stored = window.localStorage.getItem(STORAGE_KEY) === "true";
    applyCollapsedState(root, stored);

    toggleButton.addEventListener("click", () => {
      const next = root.getAttribute("data-sidebar-collapsed") !== "true";
      applyCollapsedState(root, next);
      window.localStorage.setItem(STORAGE_KEY, String(next));
    });
  }

  function initMobileDrawer() {
    const root = document.documentElement;
    const toggleButton = document.querySelector("[data-sidebar-mobile-toggle]");
    const backdrop = document.querySelector("[data-sidebar-backdrop]");
    if (!toggleButton) return;

    const close = () => root.setAttribute("data-sidebar-mobile-open", "false");
    const open = () => root.setAttribute("data-sidebar-mobile-open", "true");

    toggleButton.addEventListener("click", () => {
      const isOpen = root.getAttribute("data-sidebar-mobile-open") === "true";
      isOpen ? close() : open();
    });

    if (backdrop) {
      backdrop.addEventListener("click", close);
    }

    document.querySelectorAll(".dashboard-sidebar .sidebar-item").forEach((link) => {
      link.addEventListener("click", close);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initCollapseToggle();
    initMobileDrawer();
  });
})();
