const $ = (id) => document.getElementById(id);
const state = { jobs: [], profile: null };

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

function scoreClass(score) {
  const min = state.profile?.min_score ?? 1;
  if (score >= min * 2.5) return "good";
  if (score >= min) return "mid";
  return "low";
}

function renderProfile() {
  const p = state.profile;
  $("profile-summary").textContent = p.summary || "Edit the profile block in config/config.json.";
  const facts = [
    ["Locations", p.locations.join(", ") || "Any"],
    ["Max years asked", p.max_years_required ?? "No limit"],
    ["Posted within", p.max_days_old != null ? `${p.max_days_old} days` : "Any time"],
    ["Min score", p.min_score],
    ["Excludes", p.title_exclude.filter((t) => t.length > 2).slice(0, 6).join(", ") + "…"],
  ];
  $("profile-facts").innerHTML = facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  $("profile-skills").innerHTML = Object.entries(p.skills)
    .sort((a, b) => b[1] - a[1])
    .map(([s, w]) => `<span class="chip">${esc(s)}<b>${w}</b></span>`)
    .join("");
}

function renderSources() {
  const sources = [...new Set(state.jobs.map((j) => j.source))].sort();
  $("f-source").innerHTML =
    '<option value="">All sources</option>' +
    sources.map((s) => `<option>${esc(s)}</option>`).join("");
  const max = Math.max(1, ...state.jobs.map((j) => j.score));
  $("f-min").max = max;
}

function isoDaysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  // local date, not UTC, to match how the scraper compares dates
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function filtered() {
  const q = $("f-search").value.trim().toLowerCase();
  const source = $("f-source").value;
  const min = +$("f-min").value;
  const remote = $("f-remote").checked;
  const showAll = $("f-all").checked;
  const sort = $("f-sort").value;
  const maxAge = $("f-age").value;
  const cutoff = maxAge === "" ? "" : isoDaysAgo(+maxAge);

  const list = state.jobs.filter((j) => {
    if (!showAll && !j.eligible) return false;
    if (source && j.source !== source) return false;
    if (j.score < min) return false;
    if (cutoff && (j.posted_date || "") < cutoff) return false;
    if (remote && !j.remote) return false;
    if (q) {
      const hay = `${j.title} ${j.company} ${j.location} ${j.description_snippet} ${j.matched_skills.join(" ")}`;
      if (!hay.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  if (sort === "date") list.sort((a, b) => (b.posted_date || "").localeCompare(a.posted_date || ""));
  if (sort === "seen") list.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || b.score - a.score);
  return list;
}

function jobCard(j, maxScore) {
  const cls = scoreClass(j.score);
  const pct = Math.round((j.score / maxScore) * 100);
  const meta = [
    j.company && `<span>${esc(j.company)}</span>`,
    j.location && `<span>📍 ${esc(j.location)}</span>`,
    j.remote && `<span class="tag">Remote</span>`,
    j.remote && !j.remote_ok && `<span class="tag warn" title="Location names a region outside your allowed list">Region-locked?</span>`,
    j.salary && `<span>💰 ${esc(j.salary)}</span>`,
    j.years_required != null && `<span>${j.years_required}+ yrs</span>`,
    j.posted_date && `<span>Posted ${esc(j.posted_date)}</span>`,
    `<span>via ${esc(j.source)}</span>`,
  ].filter(Boolean).join("");
  const skills = j.matched_skills.length
    ? j.matched_skills.map((s) => `<span class="chip hit">${esc(s)}<b>+${state.profile.skills[s]}</b></span>`).join("")
    : '<span class="muted small">No profile skills mentioned</span>';

  return `
    <article class="job${j.eligible ? "" : " ineligible"}">
      <div class="rank">${j.eligible ? `#${j.rank}` : "–"}<small>${j.eligible ? "rank" : "filtered"}</small></div>
      <div>
        <a class="job-title" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a>
        <div class="meta">${meta}</div>
        <div class="chips">${skills}</div>
        ${j.description_snippet ? `<p class="desc clamp" title="Click to expand">${esc(j.description_snippet)}</p>` : ""}
        ${j.eligible ? "" : `<div class="reasons">Doesn't fit: ${esc(j.reasons.join("; "))}</div>`}
      </div>
      <div class="score">
        <div class="score-num s-${cls}">${j.score}</div>
        <div class="score-bar"><span class="bg-${cls}" style="width:${pct}%"></span></div>
        <small>match</small>
      </div>
    </article>`;
}

function render() {
  $("f-min-label").textContent = $("f-min").value;
  const list = filtered();
  const maxScore = Math.max(1, ...state.jobs.map((j) => j.score));
  $("jobs").innerHTML = list.map((j) => jobCard(j, maxScore)).join("");
  $("empty").hidden = list.length > 0;

  const eligible = state.jobs.filter((j) => j.eligible).length;
  const updated = state.profile.generated_at
    ? ` · updated ${new Date(state.profile.generated_at).toLocaleString()}` : "";
  $("stats").textContent =
    `${eligible} of ${state.jobs.length} stored jobs fit your profile · showing ${list.length}${updated}`;
}

async function load() {
  const [jobs, profile] = await Promise.all([
    fetch("api/jobs.json").then((r) => r.json()),
    fetch("api/profile.json").then((r) => r.json()),
  ]);
  state.jobs = jobs;
  state.profile = profile;
  if (profile.static) {
    // Hosted copy (GitHub Pages): data is refreshed by the daily workflow, not from here.
    $("run-btn").hidden = true;
  }
  // Default the age filter to the config's max_days_old (or "Any time").
  const age = $("f-age");
  const wanted = profile.max_days_old == null ? "" : String(profile.max_days_old);
  if (![...age.options].some((o) => o.value === wanted)) age.add(new Option(`Last ${wanted} days`, wanted), 0);
  age.value = wanted;
  renderProfile();
  renderSources();
  render();
}

async function runScraper() {
  const btn = $("run-btn");
  btn.disabled = true;
  btn.textContent = "Scraping… (can take a minute)";
  try {
    const res = await fetch("api/run", { method: "POST" });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || res.statusText);
    await load();
    btn.textContent = `Done: ${body.new} new`;
  } catch (err) {
    btn.textContent = "Run failed";
    alert(`Scrape failed: ${err.message}`);
  } finally {
    setTimeout(() => { btn.disabled = false; btn.textContent = "Run scraper"; }, 2500);
  }
}

["f-search", "f-source", "f-min", "f-remote", "f-all", "f-sort", "f-age"].forEach((id) =>
  $(id).addEventListener("input", render));
$("jobs").addEventListener("click", (e) => {
  if (e.target.classList.contains("desc")) e.target.classList.toggle("clamp");
});
$("run-btn").addEventListener("click", runScraper);

load().catch((err) => {
  $("stats").textContent = `Failed to load jobs: ${err.message}`;
});
