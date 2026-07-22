/**
 * dashboard-animations.js
 * ---------------------------------------------------------------------
 * GSAP animations specific to the dashboard: staggered entrance for
 * cards/sections, animated progress/gauge bar fills, and the processing
 * pipeline connector "draw" effect (mirrors the landing page's timeline
 * connector behavior, reused conceptually but scoped to dashboard
 * selectors since the markup differs).
 *
 * Numeric counters reuse static/js/counters.js as-is (already generic
 * and selector-driven via [data-count-to]).
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  function isReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function initEntranceAnimations() {
    const items = document.querySelectorAll("[data-animate]");
    if (!items.length) return;

    if (typeof gsap === "undefined" || isReducedMotion()) {
      return;
    }

    gsap.from(items, {
      opacity: 0,
      y: 16,
      duration: 0.5,
      ease: "power3.out",
      stagger: 0.06,
    });
  }

  function initMetricCardStagger() {
    const cards = document.querySelectorAll("[data-metric-card]");
    if (!cards.length || typeof gsap === "undefined" || isReducedMotion()) return;

    gsap.from(cards, {
      opacity: 0,
      y: 20,
      duration: 0.5,
      ease: "power3.out",
      stagger: 0.08,
      delay: 0.1,
    });
  }

  function animateFill(el, valueAttr, targetSelectorIsWidth) {
    const target = Number(el.dataset[valueAttr] || "0");
    if (typeof gsap === "undefined") {
      el.style.width = `${target}%`;
      return;
    }
    gsap.to(el, {
      width: `${target}%`,
      duration: 1.2,
      ease: "power2.out",
      delay: 0.2,
    });
  }

  function initProgressBars() {
    document.querySelectorAll("[data-progress-fill]").forEach((el) => {
      animateFill(el, "progressValue");
    });
  }

  function initGaugeBars() {
    document.querySelectorAll("[data-gauge-fill]").forEach((el) => {
      animateFill(el, "gaugeValue");
    });
  }

  function initPipelineConnectors() {
    const track = document.querySelector("[data-timeline-track]");
    if (!track) return;

    const connectors = track.querySelectorAll(".pipeline-connector.is-filled");
    if (!connectors.length) return;

    // The connectors are rendered with `.is-filled` already present
    // (reflecting server-side pipeline stage state), so the CSS
    // transition on `::after` has no state change to animate from.
    // Temporarily remove the class, then re-apply on the next frame so
    // the "fill" transition actually plays on page load.
    connectors.forEach((connector) => connector.classList.remove("is-filled"));

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        connectors.forEach((connector, index) => {
          window.setTimeout(() => {
            connector.classList.add("is-filled");
          }, index * 120);
        });
      });
    });
  }

  function init() {
    initEntranceAnimations();
    initMetricCardStagger();
    initProgressBars();
    initGaugeBars();
    initPipelineConnectors();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
