/**
 * counters.js
 * ---------------------------------------------------------------------
 * Animates the numeric statistics counters in the Statistics section.
 * Each counter tweens from 0 to its target value once, when scrolled
 * into view, using GSAP's numeric tweening via a proxy object. Values
 * with a `data-display-override` (e.g. "24/7") are revealed with a
 * simple fade instead of being numerically tweened, since they are not
 * meaningfully "countable".
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  function animateCounter(el) {
    const target = Number(el.dataset.countTo || "0");
    const prefixSymbol = el.dataset.prefixSymbol || "";
    const suffix = el.dataset.suffix || "";
    const displayOverride = el.dataset.displayOverride;

    if (displayOverride) {
      gsap.fromTo(
        el,
        { opacity: 0, y: 8 },
        { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }
      );
      return;
    }

    const proxy = { value: 0 };
    gsap.to(proxy, {
      value: target,
      duration: 1.6,
      ease: "power2.out",
      onUpdate: () => {
        el.textContent = `${prefixSymbol}${Math.round(proxy.value)}${suffix}`;
      },
    });
  }

  function initCounters() {
    const counters = document.querySelectorAll("[data-count-to], [data-display-override]");
    if (!counters.length) return;

    if (typeof gsap === "undefined") {
      counters.forEach((el) => {
        const override = el.dataset.displayOverride;
        if (override) return;
        el.textContent = `${el.dataset.prefixSymbol || ""}${el.dataset.countTo}${el.dataset.suffix || ""}`;
      });
      return;
    }

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    counters.forEach((el) => {
      if (prefersReducedMotion) {
        const override = el.dataset.displayOverride;
        el.textContent = override
          ? override
          : `${el.dataset.prefixSymbol || ""}${el.dataset.countTo}${el.dataset.suffix || ""}`;
        return;
      }

      if (typeof ScrollTrigger !== "undefined") {
        ScrollTrigger.create({
          trigger: el,
          start: "top 85%",
          once: true,
          onEnter: () => animateCounter(el),
        });
      } else {
        animateCounter(el);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initCounters);
})();
