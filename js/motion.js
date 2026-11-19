// GSAP motion layer for Karo Intelligence.
// Wraps the existing render functions in index.html so every animation confirms
// an action or guides the eye. Does nothing if GSAP failed to load, and keeps
// to instant changes when the user prefers reduced motion.
(function () {
  if (!window.gsap) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  gsap.registerPlugin(ScrollTrigger, SplitText);
  const EASE = "power3.out";

  const wrap = (name, after) => {
    const orig = window[name];
    if (typeof orig !== "function") return;
    window[name] = function () {
      const res = orig.apply(this, arguments);
      try { after.apply(this, arguments); } catch (e) { console.warn("motion:", e); }
      return res;
    };
  };

  // ── Page title: words rise out of a mask ─────────────────────────────────────
  function revealTitle(delay) {
    if (reduce) return;
    const t = document.getElementById("page-title");
    if (!t) return;
    const s = SplitText.create(t, { type: "words", mask: "words" });
    gsap.from(s.words, {
      yPercent: 110, duration: 0.75, ease: EASE, stagger: 0.07, delay: delay || 0,
      onComplete: () => s.revert(),
    });
  }

  // ── Numbers count up from their previous value ──────────────────────────────
  const lastValue = new Map();
  function countUp(nodes) {
    nodes.forEach(n => {
      const m = n.textContent.trim().match(/^(\d+)(\D*)$/);
      if (!m) return;
      const key = (n.nextElementSibling && n.nextElementSibling.textContent) || n.id;
      const end = +m[1], suffix = m[2], from = lastValue.get(key) ?? 0;
      lastValue.set(key, end);
      if (reduce || from === end) return;
      const o = { v: from };
      n.textContent = from + suffix;
      gsap.to(o, { v: end, duration: 0.9, ease: "power2.out", onUpdate: () => { n.textContent = Math.round(o.v) + suffix; } });
    });
  }

  // ── Article list: new rows fade up as they scroll in; hero parallax ─────────
  let prevIds = new Set();
  let triggers = [];
  wrap("renderArticles", function () {
    const el = document.getElementById("articles-container");
    triggers.forEach(t => t && t.kill());
    triggers = [];

    const rows = [...el.querySelectorAll(".article-featured, .article-row")];
    const ids = new Set();
    const fresh = [];
    rows.forEach(r => {
      r.classList.remove("fade-in");
      r.style.animationDelay = "";
      const b = r.querySelector(".fb-btn.up");
      const id = b ? b.id : "";
      ids.add(id);
      if (!prevIds.has(id)) fresh.push(r);
    });
    prevIds = ids; // a silent background refresh with the same articles animates nothing

    if (!reduce && fresh.length) {
      gsap.set(fresh, { autoAlpha: 0, y: 14 });
      triggers.push(...ScrollTrigger.batch(fresh, {
        start: "top 96%",
        once: true,
        onEnter: batch => gsap.to(batch, { autoAlpha: 1, y: 0, duration: 0.6, ease: EASE, stagger: 0.06, overwrite: true }),
      }));
    }

    const hero = el.querySelector(".af-hero");
    if (hero && !reduce) {
      const tw = gsap.fromTo(hero, { backgroundPosition: "50% 30%" }, {
        backgroundPosition: "50% 70%", ease: "none",
        scrollTrigger: { trigger: hero, start: "top bottom", end: "bottom top", scrub: 0.4 },
      });
      triggers.push(tw.scrollTrigger);
    }

    countUp(document.querySelectorAll("#stats-row.visible .stat-n"));
  });

  // Reset "seen" rows when the view or filters change, so the new list animates in
  ["setCat", "setBrand", "setSrc", "setDateRange", "toggleWeak", "resetFilters"].forEach(fn => {
    const orig = window[fn];
    if (typeof orig !== "function") return;
    window[fn] = function () { prevIds = new Set(); return orig.apply(this, arguments); };
  });

  // The digest is inserted above the list after it renders – re-measure triggers
  wrap("renderDigest", () => ScrollTrigger.refresh());

  // ── View switch: title reveal + content settles in ───────────────────────────
  {
    const orig = window.switchView;
    window.switchView = function () {
      prevIds = new Set();
      const res = orig.apply(this, arguments);
      revealTitle();
      if (!reduce) {
        const src = document.getElementById("sources-page");
        if (src.classList.contains("visible")) {
          gsap.from("#sources-page .sources-section", { autoAlpha: 0, y: 14, duration: 0.6, ease: EASE, stagger: 0.08 });
        }
      }
      return res;
    };
  }

  // ── Calibration: numbers count up, bars grow ─────────────────────────────────
  wrap("renderCalibration", function () {
    const page = document.getElementById("sources-page");
    if (!page.classList.contains("visible")) return;
    countUp(document.querySelectorAll(".cal-stat-n"));
    if (!reduce) gsap.from("#cal-tbody .bar", { width: 0, duration: 0.8, ease: EASE, stagger: 0.05 });
  });

  // ── Vote: a small nudge in the direction of the vote ────────────────────────
  {
    const orig = window.handleVote;
    window.handleVote = function (id, v, btn) {
      if (!reduce && btn && typeof feedback !== "undefined" && feedback[id] !== v) {
        gsap.fromTo(btn, { y: v === "up" ? 3 : -3, scale: 0.96 }, { y: 0, scale: 1, duration: 0.4, ease: "back.out(3)", clearProps: "transform" });
      }
      return orig.apply(this, arguments);
    };
  }

  // ── Modals: dialog slides up (bottom sheet on mobile) ────────────────────────
  function animateModal(id) {
    if (reduce) return;
    const overlay = document.getElementById(id);
    const box = overlay.querySelector(".modal-box");
    const mobile = window.innerWidth < 700;
    gsap.fromTo(overlay, { opacity: 0 }, { opacity: 1, duration: 0.25, ease: "power1.out", clearProps: "opacity" });
    gsap.fromTo(box, mobile ? { yPercent: 100 } : { y: 18, opacity: 0 },
      { yPercent: 0, y: 0, opacity: 1, duration: 0.46, ease: "expo.out", clearProps: "transform,opacity" });
  }
  wrap("openAddModal", () => animateModal("add-modal"));
  wrap("openEditModal", () => animateModal("edit-modal"));

  // ── Theme button: half turn per tap ─────────────────────────────────────────
  wrap("toggleTheme", () => {
    if (!reduce) gsap.to("#theme-btn", { rotation: "+=180", duration: 0.45, ease: "power2.inOut" });
  });

  // ── Add button: soft quarter turn on hover ──────────────────────────────────
  const add = document.querySelector(".add-btn");
  if (add && !reduce) {
    add.addEventListener("pointerenter", () => gsap.to(add, { rotation: 90, duration: 0.35, ease: EASE }));
    add.addEventListener("pointerleave", () => gsap.to(add, { rotation: 0, duration: 0.35, ease: EASE }));
  }

  // ── First load: reveal the title once the splash has lifted ─────────────────
  revealTitle(document.getElementById("splash") ? 2.0 : 0.1);
  // Articles rendered before this script ran: animate what is already on screen
  if (document.querySelector("#articles-container .article-row, #articles-container .article-featured")) {
    window.renderArticles(typeof lastRendered !== "undefined" ? lastRendered : []);
  }
})();
