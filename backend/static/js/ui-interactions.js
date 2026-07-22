/**
 * ui-interactions.js
 * ---------------------------------------------------------------------
 * Small, framework-independent UI interaction behaviors that are not
 * tied to scroll-triggered animation (handled in gsap-animations.js).
 * Currently: button ripple effect on `.ds-btn` elements.
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  function attachRipple(button) {
    button.addEventListener("pointerdown", (event) => {
      const rect = button.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 1.2;
      const ripple = document.createElement("span");

      ripple.className = "ds-btn__ripple";
      ripple.style.width = `${size}px`;
      ripple.style.height = `${size}px`;
      ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
      ripple.style.top = `${event.clientY - rect.top - size / 2}px`;

      button.appendChild(ripple);
      ripple.addEventListener("animationend", () => ripple.remove());
    });
  }

  function initButtonRipples() {
    document.querySelectorAll(".ds-btn").forEach(attachRipple);
  }

  document.addEventListener("DOMContentLoaded", initButtonRipples);
})();
