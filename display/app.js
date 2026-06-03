/* =========================================================================
   app.js — the brains of the display.
   =========================================================================

   Responsibilities:
     • Load signage.json (written weekly by the updater).
     • Pick today's seasonal skin from themes.json and apply it.
     • Render the schedule, yard duty, coming-up strip, ticker.
     • Compute the live "happening now / up next" banner.   (surprise #1)
     • Draw scan-to-log QR codes for the house-points forms.  (surprise #2)
     • Keep it all fresh on timers — no one should touch the kiosk.
       The JSON re-loads every few minutes so a new weekly run just appears.

   House points live in the soarpoints iframe — no Supabase needed here.

   No localStorage / sessionStorage anywhere (kiosk sandboxing).
   ========================================================================= */

"use strict";

/* -------------------------------------------------------------------------
   CONFIG — the bits you'll edit. Everything else is logic you can leave alone.
   ------------------------------------------------------------------------- */
const CONFIG = {
  // ---- Scan-to-log forms (surprise #2) ----
  // Paste the Google Form share links from the bulletin here. They become QR
  // codes staff can scan off the wall to log from their phone.
  // url: null + placeholder: true → renders an empty dashed "reserved" tile.
  forms: [
    { label: "House Points", url: "https://soarpoints.web.app" },
    { label: "Work Order",   url: "https://docs.google.com/forms/d/e/1FAIpQLSecmNhWMgJS66Z0pOvKgm3SN59iCmgd9UVe6YIE7558d-9H_g/viewform" },
  ],

  // ---- Countdown chip (top-right). Set to null to hide. ----
  // Shows "N days to <label>". Refresh the date each year.
  countdownTo: { label: "Last Day", date: "2026-06-12" },

  // Shown in the ticker when there are no announcements, so the bar is always present.
  tickerFallback: "SOAR Charter Academy",

  // ---- Refresh cadences (milliseconds) ----
  reloadSignageMs: 5 * 60 * 1000,  // re-read signage.json (catch a new weekly run)
  tickMs: 30 * 1000,               // re-evaluate now/next, theme, countdown
};

/* In-memory state. */
const STATE = {
  signage: null,
  themeKey: "default",
  effectFor: "none",
};

/* ====================== tiny DOM helpers ====================== */
const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

/* ====================== date / time utilities ====================== */
function todayLocal() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

/** Parse an ISO "YYYY-MM-DD" as a LOCAL date (avoids UTC off-by-one). */
function parseISODate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

/** "HH:MM" 24h → minutes since midnight, or null. */
function timeToMinutes(hhmm) {
  if (!hhmm) return null;
  const [h, m] = hhmm.split(":").map(Number);
  if (Number.isNaN(h)) return null;
  return h * 60 + (m || 0);
}

/** "14:00" → "2:00p" (compact, glanceable). */
function prettyTime(hhmm) {
  const mins = timeToMinutes(hhmm);
  if (mins == null) return "";
  let h = Math.floor(mins / 60);
  const m = mins % 60;
  const ampm = h >= 12 ? "p" : "a";
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, "0")}${ampm}`;
}

/** End of the current school week (Sunday), for bucketing events. */
function endOfWeek(from) {
  const d = new Date(from);
  const dow = (d.getDay() + 6) % 7; // Mon=0 … Sun=6
  d.setDate(d.getDate() + (6 - dow));
  d.setHours(23, 59, 59, 999);
  return d;
}

/* ====================== data load ====================== */
async function loadSignage() {
  try {
    const res = await fetch(`data/signage.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    STATE.signage = await res.json();
  } catch (err) {
    console.error("Could not load signage.json:", err);
    if (!STATE.signage) STATE.signage = { events: [], yard_duty: {}, announcements: [] };
  }
  renderAll();
}

/* ====================== THEME ENGINE ====================== */
let THEMES = null;

async function loadThemes() {
  try {
    const res = await fetch(`themes/themes.json?t=${Date.now()}`);
    THEMES = await res.json();
  } catch (err) {
    console.error("Could not load themes.json — staying on default:", err);
    THEMES = { order: ["default"], themes: { default: { label: "Staff Board", effect: "none" } } };
  }
}

/** Is today's MM-DD inside [from,to]? Handles wrap-around windows (e.g. Dec→Jan). */
function inWindow(monthDay, from, to) {
  if (from <= to) return monthDay >= from && monthDay <= to;
  return monthDay >= from || monthDay <= to;
}

function pickThemeKey() {
  // 1) URL override, for previewing: index.html?theme=halloween
  const urlTheme = new URLSearchParams(location.search).get("theme");
  if (urlTheme && THEMES.themes[urlTheme]) return urlTheme;

  // 2) Updater-set override written into the JSON.
  const jsonOverride = STATE.signage && STATE.signage.theme_override;
  if (jsonOverride && THEMES.themes[jsonOverride]) return jsonOverride;

  // 3) Auto by date. Walk themes in priority order; first window match wins,
  //    so a specific holiday beats the broad season it sits inside.
  const now = new Date();
  const mmdd = `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  for (const key of THEMES.order) {
    const theme = THEMES.themes[key];
    if (!theme || !theme.active) continue;
    for (const w of theme.active) {
      if (inWindow(mmdd, w.from, w.to)) return key;
    }
  }
  return "default";
}

function applyTheme() {
  const key = pickThemeKey();
  STATE.themeKey = key;
  const theme = THEMES.themes[key] || {};

  document.documentElement.setAttribute("data-theme", key);
  $("#seasonLabel").textContent = theme.label || "Staff Board";

  const effect = theme.effect || "none";
  if (effect !== STATE.effectFor && window.Effects) {
    STATE.effectFor = effect;
    window.Effects.set(effect);
  }
}

/* ====================== RENDER: schedule ====================== */
function renderSchedule() {
  const wrap = $("#schedule");
  wrap.innerHTML = "";

  const events = (STATE.signage.events || []).filter((e) => e && e.title);
  const today = todayLocal();
  const weekEnd = endOfWeek(today);

  const thisWeek = [];
  for (const e of events) {
    const d = parseISODate(e.date);
    if (d == null) { thisWeek.push({ ...e, _date: null }); continue; }
    if (d < today) continue;
    if (d <= weekEnd) thisWeek.push({ ...e, _date: d });
  }

  const byDay = new Map();
  for (const e of thisWeek) {
    const key = e._date ? e._date.toDateString() : "anytime";
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(e);
  }

  const dayKeys = [...byDay.keys()].sort((a, b) => {
    if (a === "anytime") return 1;
    if (b === "anytime") return -1;
    return new Date(a) - new Date(b);
  });

  if (dayKeys.length === 0) {
    wrap.appendChild(el("p", "duty__empty", "No events scheduled for the rest of the week."));
    return;
  }

  const todayStr = today.toDateString();
  for (const key of dayKeys) {
    const isToday = key === todayStr;
    const card = el("div", `day${isToday ? " day--today" : ""}`);

    const head = el("div", "day__head");
    const date = key === "anytime" ? null : new Date(key);
    head.appendChild(el("span", "day__name",
      key === "anytime" ? "This Week" : date.toLocaleDateString(undefined, { weekday: "long" })));
    if (isToday) head.appendChild(el("span", "day__tag", "Today"));
    if (date) head.appendChild(el("span", "day__date",
      date.toLocaleDateString(undefined, { month: "short", day: "numeric" })));
    card.appendChild(head);

    const items = byDay.get(key).sort((a, b) => {
      const ta = timeToMinutes(a.start), tb = timeToMinutes(b.start);
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return ta - tb;
    });

    for (const e of items) {
      const row = el("div", "evt");
      row.appendChild(el("span", "evt__time", e.start ? prettyTime(e.start) : "—"));
      const dot = el("span", "evt__dot");
      dot.style.background = `var(--cat-${e.category || "general"})`;
      row.appendChild(dot);
      row.appendChild(el("span", "evt__title", e.title));
      if (e.location) row.appendChild(el("span", "evt__loc", e.location));
      if (e.audience) row.appendChild(el("span", "evt__aud", e.audience));
      card.appendChild(row);
    }
    wrap.appendChild(card);
  }

  // After layout settles, trim any day-card that can't fully fit so This Week
  // never shows a card cut off mid-content (it shows complete cards only).
  requestAnimationFrame(() => fitSchedule(wrap));
}

// Keep only the day-cards that fully fit the schedule's visible height; remove
// the first one that would overflow and everything after it. Always keeps at
// least the first card.
function fitSchedule(wrap) {
  const maxH = wrap.clientHeight;
  if (!maxH) return;
  const gap = parseFloat(getComputedStyle(wrap).gap) || 8;
  const cards = [...wrap.children];
  let used = 0;
  for (let i = 0; i < cards.length; i++) {
    used += (i > 0 ? gap : 0) + cards[i].offsetHeight;
    if (used > maxH + 2) {   // tolerance: avoids sub-pixel false-clips when content-sized
      cards.slice(i === 0 ? 1 : i).forEach((c) => c.remove());
      break;
    }
  }
}

/* ====================== SURPRISE #1: now / up next ====================== */
function renderNowNext() {
  const banner = $("#nowNext");
  const today = todayLocal();
  const todayEvents = (STATE.signage.events || [])
    .map((e) => ({ ...e, _date: parseISODate(e.date) }))
    .filter((e) => e._date && e._date.getTime() === today.getTime() && timeToMinutes(e.start) != null)
    .sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));

  if (todayEvents.length === 0) { banner.hidden = true; return; }

  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();

  const happening = todayEvents.find((e) => {
    const s = timeToMinutes(e.start);
    const end = timeToMinutes(e.end) ?? s + 60;
    return nowMin >= s && nowMin <= end;
  });
  const upNext = todayEvents.find((e) => timeToMinutes(e.start) > nowMin);

  if (!happening && !upNext) { banner.hidden = true; return; }
  banner.hidden = false;

  const nowCell = $(".nownext__cell--now");
  if (happening) {
    nowCell.style.display = "";
    $("#nowTitle").textContent = happening.title;
    nowCell.classList.add("pulse");
  } else {
    nowCell.style.display = "none";
    nowCell.classList.remove("pulse");
  }

  const nextCell = $(".nownext__cell--next");
  if (upNext) {
    nextCell.style.display = "";
    $("#nextTitle").textContent = `${prettyTime(upNext.start)} · ${upNext.title}`;
  } else {
    nextCell.style.display = "none";
  }
}

/* ====================== yard duty (full day, current period highlighted) ====================== */
// Shows the WHOLE day's posts, grouped Morning / Midday / Afternoon. The group
// matching the current clock time gets highlighted so the eye lands on what's
// relevant right now — without hiding the rest of the day.
function currentDutyPeriod() {
  const nowMins = new Date().getHours() * 60 + new Date().getMinutes();
  const GRACE   = 20; // minutes after a period's last shift ends before the next becomes "now"

  // Parse each assignment's time string ("7:30–7:45a", "3:10–3:20p") to find the
  // latest end-time (in minutes since midnight) for a given period.
  // Returns -1 when no parseable times exist (e.g. "Nutrition", "Recess").
  const assignments = (STATE.signage.yard_duty?.assignments) || [];
  function latestEnd(part) {
    let max = -1;
    for (const a of assignments) {
      if (a.part !== part) continue;
      const m = (a.time || "").match(/(\d+):(\d+)([ap])\s*$/i); // end time is last H:MMa/p
      if (!m) continue;
      let h = +m[1];
      if (m[3].toLowerCase() === "p" && h !== 12) h += 12;
      if (m[3].toLowerCase() === "a" && h === 12) h  = 0;
      max = Math.max(max, h * 60 + +m[2]);
    }
    return max;
  }

  const amEnd  = latestEnd("am");   // e.g. 475 for 7:55 a.m.
  const midEnd = latestEnd("mid");  // -1 if midday slots have no clock times

  // Prefer actual shift end + grace; fall back to hard thresholds when end
  // time is unknown (Nutrition / Recess labels can't be parsed to a clock time).
  const amToMid = amEnd  >= 0 ? amEnd  + GRACE : 10 * 60 + 30;
  const midToPm = midEnd >= 0 ? midEnd + GRACE : 13 * 60 + 30;

  if (nowMins < amToMid) return "am";
  if (nowMins < midToPm) return "mid";
  return "pm";
}

const PERIOD_LABELS = { am: "Morning", mid: "Midday", pm: "Afternoon" };

function renderDuty() {
  const wrap = $("#duty");
  wrap.innerHTML = "";

  const duty = STATE.signage.yard_duty || {};
  const assignments = duty.assignments || [];
  $("#dutyWeek").textContent = duty.week_label || "";

  if (assignments.length === 0) {
    wrap.appendChild(el("p", "duty__empty", "No duty scheduled."));
    return;
  }

  const period = currentDutyPeriod();
  const groups = { am: [], mid: [], pm: [] };
  for (const a of assignments) (groups[a.part] || groups.mid).push(a);

  for (const part of ["am", "mid", "pm"]) {
    if (groups[part].length === 0) continue;
    const isCurrent = part === period;

    const group = el("div", `duty__group${isCurrent ? " duty__group--current" : ""}`);

    const label = el("div", "duty__group-label");
    label.textContent = PERIOD_LABELS[part];
    if (isCurrent) {
      const dot = el("span", "duty__now-dot", " ● now");
      label.appendChild(dot);
    }
    group.appendChild(label);

    for (const a of groups[part]) {
      const row = el("div", "duty__row");
      row.appendChild(el("span", "duty__time",  a.time  || ""));
      row.appendChild(el("span", "duty__name",  a.name));
      row.appendChild(el("span", "duty__where", a.where || ""));
      group.appendChild(row);
    }
    wrap.appendChild(group);
  }
}

/* ====================== SURPRISE #2: scan-to-log QR ====================== */
function renderScan() {
  const wrap = $("#scan");
  wrap.innerHTML = "";

  CONFIG.forms.forEach((form) => {
    const tile = el("div", `scan__tile${form.placeholder ? " scan__tile--placeholder" : ""}`);
    const qr = el("div", "scan__qr");
    tile.appendChild(qr);
    tile.appendChild(el("span", "scan__label", form.label));
    wrap.appendChild(tile);

    // Reserved seasonal slot — empty dashed box until a URL is added in CONFIG.
    if (form.placeholder || !form.url) {
      qr.classList.add("scan__qr--empty");
      qr.appendChild(el("span", "scan__hint", "add link"));
      return;
    }

    if (window.QRCode) {
      new window.QRCode(qr, {
        text: form.url,
        width: 200, height: 200,
        colorDark: "#0b0f17", colorLight: "#ffffff",
        correctLevel: window.QRCode.CorrectLevel.M,
      });
    } else {
      // CDN didn't load (offline kiosk?) — show the short URL as fallback.
      const link = el("span", "duty__empty", form.url.replace(/^https?:\/\//, "").slice(0, 22));
      link.style.fontSize = "10px";
      qr.appendChild(link);
    }
  });
}

/* ====================== coming up strip ====================== */
function renderComingUp() {
  const track = $("#comingUp");
  if (!track) return;   // Coming Up was removed from the layout — bail before touching it
  track.innerHTML = "";
  const today = todayLocal();
  const weekEnd = endOfWeek(today);

  const upcoming = (STATE.signage.events || [])
    .map((e) => ({ ...e, _date: parseISODate(e.date) }))
    .filter((e) => e._date && e._date > weekEnd)
    .sort((a, b) => a._date - b._date)
    .slice(0, 12);

  if (upcoming.length === 0) {
    track.appendChild(el("span", "chip", "Nothing on the horizon yet"));
    return;
  }
  for (const e of upcoming) {
    const chip = el("span", "chip");
    chip.appendChild(el("span", "chip__date",
      e._date.toLocaleDateString(undefined, { month: "short", day: "numeric" })));
    chip.appendChild(el("span", "chip__title", e.title));
    track.appendChild(chip);
  }
}

/* ====================== ticker (announcements) ====================== */
function renderTicker() {
  const wrap = $("#tickerWrap");
  const track = $("#ticker");
  let items = STATE.signage.announcements || [];
  if (items.length === 0) items = [{ text: CONFIG.tickerFallback || "" }];
  wrap.hidden = false;

  track.innerHTML = "";
  for (let pass = 0; pass < 2; pass++) {
    for (const a of items) {
      const span = el("span", `ticker__item${a.priority === "high" ? " ticker__item--high" : ""}`, a.text);
      track.appendChild(span);
    }
  }
  const seconds = Math.max(30, items.reduce((n, a) => n + a.text.length, 0) * 0.35);
  track.style.setProperty("--ticker-duration", `${seconds}s`);
}

/* ====================== clock + countdown + stamp ====================== */
function renderClock() {
  const now = new Date();
  $("#clockTime").textContent = now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  $("#clockDate").textContent = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function renderCountdown() {
  const chip = $("#countdown");
  if (!CONFIG.countdownTo) { chip.hidden = true; return; }
  const target = parseISODate(CONFIG.countdownTo.date);
  if (!target) { chip.hidden = true; return; }
  const days = Math.ceil((target - todayLocal()) / 86400000);
  if (days < 0) { chip.hidden = true; return; }
  chip.hidden = false;
  chip.textContent = days === 0
    ? `${CONFIG.countdownTo.label} is today!`
    : `${days} day${days === 1 ? "" : "s"} to ${CONFIG.countdownTo.label}`;
}

function renderStamp() {
  const gen = STATE.signage && STATE.signage.generated_at;
  const when = gen ? new Date(gen).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";
  $("#stamp").textContent = `live · bulletin ${when}`;
}

/* ====================== orchestration ====================== */
function renderAll() {
  applyTheme();
  renderSchedule();
  renderNowNext();
  renderDuty();
  renderScan();
  renderComingUp();
  renderTicker();
  renderClock();
  renderCountdown();
  renderStamp();
}

function tick() {
  renderClock();
  renderNowNext();
  renderCountdown();
  renderDuty();   // re-evaluates the current time period every 30s
  applyTheme();
}

async function boot() {
  await loadThemes();
  await loadSignage();

  // Web fonts change line heights when they swap in; re-fit the schedule once
  // they're ready so the clip math matches what's actually on screen.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => renderSchedule());
  }

  setInterval(renderClock, 1000);
  setInterval(tick, CONFIG.tickMs);
  setInterval(loadSignage, CONFIG.reloadSignageMs);
}

document.addEventListener("DOMContentLoaded", boot);
