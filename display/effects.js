/* =========================================================================
   effects.js — optional ambient particles (snow · leaves · confetti).
   =========================================================================

   A skin opts in by setting "effect" in themes.json; app.js calls
   Effects.set("snow" | "leaves" | "confetti" | "none"). Everything is lazy:
   nothing animates until a mode is set, and it stops dead on "none".

   It's deliberately featherweight — a capped particle count on a single
   full-screen canvas, one requestAnimationFrame loop, and it bows out entirely
   if the viewer prefers reduced motion. Pure decoration; if this file never
   loads, the board doesn't care.
   ========================================================================= */

(function () {
  "use strict";

  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const canvas = document.getElementById("fx");
  const ctx = canvas ? canvas.getContext("2d") : null;

  let mode = "none";
  let particles = [];
  let rafId = null;
  let width = 0, height = 0;

  function resize() {
    if (!canvas) return;
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  // ---- per-mode tuning ----------------------------------------------------
  // count is capped low on purpose; this runs for hours on modest kiosk HW.
  const SPECS = {
    snow:     { count: 90,  make: makeSnow,     step: stepFall },
    leaves:   { count: 36,  make: makeLeaf,     step: stepFall },
    confetti: { count: 140, make: makeConfetti, step: stepFall },
  };

  function rand(min, max) { return min + Math.random() * (max - min); }

  function makeSnow() {
    return {
      x: rand(0, width), y: rand(-height, 0),
      r: rand(1.5, 4), vy: rand(0.4, 1.4), vx: rand(-0.4, 0.4),
      sway: rand(0, Math.PI * 2), swaySpeed: rand(0.01, 0.03),
      color: "rgba(255,255,255,0.9)", shape: "dot",
    };
  }

  function makeLeaf() {
    const palette = ["#e8852b", "#c4622a", "#d9a441", "#9c7d2f", "#b5482a"];
    return {
      x: rand(0, width), y: rand(-height, 0),
      r: rand(6, 12), vy: rand(0.6, 1.6), vx: rand(-0.6, 0.6),
      sway: rand(0, Math.PI * 2), swaySpeed: rand(0.01, 0.025),
      spin: rand(0, Math.PI * 2), spinSpeed: rand(-0.05, 0.05),
      color: palette[(Math.random() * palette.length) | 0], shape: "leaf",
    };
  }

  function makeConfetti() {
    const palette = ["#ffc64a", "#ff79c6", "#5be0a0", "#7cf0ff", "#ff7a59", "#b6ff3a"];
    return {
      x: rand(0, width), y: rand(-height, 0),
      r: rand(4, 8), vy: rand(1.2, 3.0), vx: rand(-1.0, 1.0),
      sway: rand(0, Math.PI * 2), swaySpeed: rand(0.02, 0.05),
      spin: rand(0, Math.PI * 2), spinSpeed: rand(-0.2, 0.2),
      color: palette[(Math.random() * palette.length) | 0], shape: "rect",
    };
  }

  // Shared falling integrator with gentle horizontal sway + recycle at bottom.
  function stepFall(p) {
    p.sway += p.swaySpeed;
    p.x += p.vx + Math.sin(p.sway) * 0.6;
    p.y += p.vy;
    if (p.spinSpeed) p.spin += p.spinSpeed;
    if (p.y > height + 20) { p.y = rand(-40, -10); p.x = rand(0, width); }
    if (p.x > width + 20) p.x = -20;
    if (p.x < -20) p.x = width + 20;
  }

  function draw(p) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.fillStyle = p.color;
    if (p.shape === "dot") {
      ctx.beginPath();
      ctx.arc(0, 0, p.r, 0, Math.PI * 2);
      ctx.fill();
    } else if (p.shape === "rect") {
      ctx.rotate(p.spin);
      ctx.fillRect(-p.r / 2, -p.r, p.r, p.r * 2);
    } else if (p.shape === "leaf") {
      ctx.rotate(p.spin);
      ctx.beginPath();
      ctx.ellipse(0, 0, p.r, p.r * 0.55, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function frame() {
    if (!ctx || mode === "none") return;
    ctx.clearRect(0, 0, width, height);
    const spec = SPECS[mode];
    for (const p of particles) {
      spec.step(p);
      draw(p);
    }
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId == null) rafId = requestAnimationFrame(frame);
  }
  function stop() {
    if (rafId != null) { cancelAnimationFrame(rafId); rafId = null; }
    if (ctx) ctx.clearRect(0, 0, width, height);
  }

  function set(next) {
    // Honor reduced-motion by simply never animating.
    if (prefersReduced) { mode = "none"; stop(); return; }
    if (!SPECS[next]) { mode = "none"; particles = []; stop(); return; }
    mode = next;
    const spec = SPECS[mode];
    particles = Array.from({ length: spec.count }, spec.make);
    start();
  }

  // Public surface used by app.js.
  window.Effects = { set };
})();
