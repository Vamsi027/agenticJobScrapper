import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from "./config.js";

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
const $ = (id) => document.getElementById(id);
const state = { user: null, applicant: null, jobs: [], loadedArgs: null, skillFilter: null };

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

// Profile fields the browser is allowed to change (see the column grants in the migrations).
const EDITABLE = ["name", "target_roles", "locations", "open_to_remote", "remote_allowed_regions",
  "skills", "title_include", "max_years_required", "min_score", "max_days_old"];

// ---------------------------------------------------------------- views

function show(view) {
  for (const v of ["signin", "upload", "matches"]) $(`view-${v}`).hidden = v !== view;
  $("account").hidden = !state.user;
  $("account-email").textContent = state.user?.email ?? "";
}

async function route() {
  const { data: { session } } = await supabase.auth.getSession();
  state.user = session?.user ?? null;
  if (!state.user) {
    $("stats").textContent = "Sign in to see jobs matched to your resume.";
    return show("signin");
  }
  const { data, error } = await supabase.from("applicant").select("*").eq("user_id", state.user.id).maybeSingle();
  if (error) {
    $("stats").textContent = `Could not load your profile: ${error.message}`;
    return show("matches");
  }
  state.applicant = data;
  if (!data) return showUpload(false);
  showMatches();
}

let routing = null;
function routeOnce() {
  routing ??= route().finally(() => (routing = null));
  return routing;
}

function showUpload(replacing) {
  $("upload-title").textContent = replacing ? "Replace your resume" : "Upload your resume";
  $("upload-cancel").hidden = !replacing;
  $("upload-msg").textContent = "";
  $("stats").textContent = replacing ? "Your profile will be rebuilt from the new resume." : "One step left: upload your resume.";
  show("upload");
}

async function showMatches() {
  show("matches");
  renderProfile();
  const age = $("f-age");
  const wanted = state.applicant.max_days_old == null ? "" : String(state.applicant.max_days_old);
  if (![...age.options].some((o) => o.value === wanted)) age.add(new Option(`Last ${wanted} days`, wanted), 0);
  age.value = wanted;
  await loadJobs(true);
}

// ---------------------------------------------------------------- auth

$("signin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("signin-email").value.trim();
  const btn = e.submitter;
  btn.disabled = true;
  $("signin-msg").textContent = "Sending…";
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: window.location.origin + window.location.pathname },
  });
  btn.disabled = false;
  $("signin-msg").textContent = error
    ? `Could not send the link: ${error.message}`
    : `Check ${email} for a sign-in link. You can close this tab.`;
});

$("signout-btn").addEventListener("click", async () => {
  await supabase.auth.signOut();
  Object.assign(state, { user: null, applicant: null, jobs: [], loadedArgs: null, skillFilter: null });
  routeOnce();
});

supabase.auth.onAuthStateChange((event) => {
  // SIGNED_IN fires after the magic link redirect; ignore token refreshes.
  // Deferred: calling Supabase inside this callback can deadlock supabase-js.
  if (event === "SIGNED_IN" && !state.user) setTimeout(routeOnce, 0);
});

// ---------------------------------------------------------------- resume upload

const dropZone = $("drop-zone");
$("upload-file").addEventListener("change", () => {
  const file = $("upload-file").files[0];
  $("drop-label").textContent = file ? file.name : "Drop your resume here or browse";
});
["dragenter", "dragover"].forEach((t) => dropZone.addEventListener(t, (e) => {
  e.preventDefault();
  dropZone.classList.add("over");
}));
["dragleave", "drop"].forEach((t) => dropZone.addEventListener(t, () => dropZone.classList.remove("over")));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) {
    $("upload-file").files = e.dataTransfer.files;
    $("upload-file").dispatchEvent(new Event("change"));
  }
});

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("upload-file").files[0];
  if (!file) return;
  const name = file.name.toLowerCase();
  const ext = name.endsWith(".pdf") ? "pdf" : name.endsWith(".txt") ? "txt" : null;
  if (!ext) return ($("upload-msg").textContent = "Please choose a PDF or .txt file.");
  if (file.size > 10 * 1024 * 1024) return ($("upload-msg").textContent = "That file is over 10 MB.");

  const btn = $("upload-btn");
  btn.disabled = true;
  try {
    $("upload-msg").textContent = "Uploading…";
    const path = `${state.user.id}/resume.${ext}`;
    const { error: upError } = await supabase.storage.from("resumes").upload(path, file, {
      upsert: true,
      contentType: ext === "pdf" ? "application/pdf" : "text/plain",
    });
    if (upError) throw new Error(upError.message);

    $("upload-msg").textContent = "Reading your resume… this can take up to a minute.";
    const { data, error } = await supabase.functions.invoke("parse-resume", { body: { path } });
    if (error) {
      const detail = await error.context?.json?.().catch(() => null);
      throw new Error(detail?.error || error.message);
    }
    state.applicant = data.applicant;
    $("upload-form").reset();
    $("drop-label").textContent = "Drop your resume here or browse";
    await showMatches();
  } catch (err) {
    $("upload-msg").textContent = `Failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

$("replace-btn").addEventListener("click", () => showUpload(true));
$("upload-cancel").addEventListener("click", () => showMatches());

// ---------------------------------------------------------------- profile editing (autosave)

let saveTimer = null;
let saving = Promise.resolve();

function setStatus(text, kind = "") {
  const el = $("save-status");
  el.textContent = text;
  el.className = `save-status ${kind}`;
}

/** Apply a change locally, re-render, and save after a short pause. */
function update(changes) {
  Object.assign(state.applicant, changes);
  renderProfile();
  setStatus("Unsaved…");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 600);
}

async function save() {
  await saving; // one save at a time, in order
  saving = (async () => {
    setStatus("Saving…");
    const changes = Object.fromEntries(EDITABLE.map((k) => [k, state.applicant[k]]));
    const { data, error } = await supabase.from("applicant").update(changes)
      .eq("user_id", state.user.id).select().single();
    if (error) return setStatus(`Not saved: ${error.message}`, "error");
    state.applicant = data;
    setStatus("Saved ✓", "ok");
    await loadJobs(true);
  })();
  return saving;
}

const chip = (label, attrs, extra = "") =>
  `<span class="chip removable">${esc(label)}${extra}<button type="button" ${attrs} aria-label="Remove ${esc(label)}">×</button></span>`;

function renderProfile() {
  const a = state.applicant;
  if (document.activeElement !== $("p-name")) $("p-name").value = a.name ?? "";
  $("p-headline").textContent = a.headline ?? "";

  $("p-roles").innerHTML = (a.target_roles || []).map((r, i) => chip(r, `data-remove="target_roles" data-i="${i}"`)).join("")
    || '<span class="muted small">No target roles: every title counts.</span>';

  $("p-locations").innerHTML = (a.locations || []).map((p, i) =>
    chip([p.city, p.country_code || p.country].filter(Boolean).join(", "), `data-remove="locations" data-i="${i}"`)).join("")
    || '<span class="muted small">No cities: only remote jobs match.</span>';
  $("p-remote").checked = !!a.open_to_remote;

  const skills = Object.entries(a.skills || {}).sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]));
  $("p-skills").innerHTML = skills.map(([s, w]) => `
    <div class="skill-row">
      <span class="skill-name">${esc(s)}</span>
      <span class="weights" role="group" aria-label="Weight for ${esc(s)}">
        ${[1, 2, 3].map((n) => `<button type="button" class="w${n === w ? " on" : ""}" data-skill="${esc(s)}" data-weight="${n}" title="${["", "familiar", "solid", "core"][n]}">${n}</button>`).join("")}
      </span>
      <button type="button" class="x" data-remove-skill="${esc(s)}" aria-label="Remove ${esc(s)}">×</button>
    </div>`).join("") || '<span class="muted small">Add skills to score jobs.</span>';

  const maxScore = Math.max(20, skills.reduce((t, [, w]) => t + w, 0));
  $("p-min-score").max = Math.min(maxScore, 40);
  $("p-min-score").value = a.min_score ?? 1;
  $("p-min-score-label").textContent = a.min_score ?? 1;
  $("p-max-years").textContent = a.max_years_required == null ? "no limit" : `${a.max_years_required} years`;

  $("p-include").innerHTML = (a.title_include || []).map((t, i) => chip(t, `data-remove="title_include" data-i="${i}"`)).join("")
    || '<span class="muted small">Any title.</span>';
  $("p-regions").innerHTML = (a.remote_allowed_regions || []).map((t, i) => chip(t, `data-remove="remote_allowed_regions" data-i="${i}"`)).join("");
}

$("p-name").addEventListener("input", (e) => update({ name: e.target.value.trim() || null }));
$("p-remote").addEventListener("change", (e) => update({ open_to_remote: e.target.checked }));
$("p-min-score").addEventListener("input", (e) => {
  $("p-min-score-label").textContent = e.target.value;
  update({ min_score: Number(e.target.value) });
});
document.querySelectorAll(".stepper button").forEach((b) => b.addEventListener("click", () => {
  const cur = state.applicant.max_years_required;
  let next = (cur ?? 10) + Number(b.dataset.step);
  if (cur == null && b.dataset.step > 0) return;          // already "no limit"
  if (next > 15) next = null;                             // past 15 means no limit
  update({ max_years_required: next == null ? null : Math.max(0, next) });
}));

// Remove buttons on chips and skill rows, and weight buttons.
$("view-matches").addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.dataset.remove) {
    const field = t.dataset.remove;
    update({ [field]: state.applicant[field].filter((_, i) => i !== Number(t.dataset.i)) });
  } else if (t.dataset.removeSkill) {
    const { [t.dataset.removeSkill]: _, ...rest } = state.applicant.skills;
    update({ skills: rest });
  } else if (t.dataset.weight) {
    update({ skills: { ...state.applicant.skills, [t.dataset.skill]: Number(t.dataset.weight) } });
  }
});

// "Add" forms.
document.querySelectorAll("form.add-row").forEach((form) => form.addEventListener("submit", (e) => {
  e.preventDefault();
  const a = state.applicant;
  const input = form.querySelector("input");
  const value = input.value.trim();
  if (!value) return;
  const addUnique = (arr, v) => (arr || []).some((x) => x.toLowerCase() === v.toLowerCase()) ? arr : [...(arr || []), v];
  switch (form.dataset.add) {
    case "roles":
      update({ target_roles: addUnique(a.target_roles, value) });
      break;
    case "include":
      update({ title_include: addUnique(a.title_include, value.toLowerCase()) });
      break;
    case "regions":
      update({ remote_allowed_regions: addUnique(a.remote_allowed_regions, value.toLowerCase()) });
      break;
    case "skills":
      update({ skills: { ...a.skills, [value.toLowerCase()]: Number(form.querySelector("select").value) } });
      break;
    case "locations": {
      const code = form.elements.code.value.trim().toUpperCase();
      if ((a.locations || []).some((p) => (p.city || "").toLowerCase() === value.toLowerCase())) break;
      update({ locations: [...(a.locations || []), { city: value, country: "", country_code: code }] });
      form.elements.code.value = "";
      break;
    }
  }
  input.value = "";
  input.focus();
}));

// ---------------------------------------------------------------- jobs

async function loadJobs(force = false) {
  const age = $("f-age").value;
  const args = {
    p_max_days: age === "" ? null : Number(age),
    p_include_ineligible: $("f-all").checked,
    p_limit: $("f-all").checked ? 1500 : null, // all matches; non-matches capped
  };
  const key = JSON.stringify(args);
  if (!force && key === state.loadedArgs) return render();
  $("jobs").classList.add("loading");
  const { data, error } = await supabase.rpc("match_jobs", args);
  $("jobs").classList.remove("loading");
  if (error) {
    $("stats").textContent = `Failed to load jobs: ${error.message}`;
    return;
  }
  state.jobs = data;
  state.loadedArgs = key;
  let rank = 0;
  for (const j of state.jobs) if (j.eligible) j.rank = ++rank;
  renderSources();
  render();
}

function scoreClass(score) {
  const min = state.applicant?.min_score ?? 1;
  if (score >= min * 2.5) return "good";
  if (score >= min) return "mid";
  return "low";
}

function renderSources() {
  const current = $("f-source").value;
  const sources = [...new Set(state.jobs.map((j) => j.source.split(":")[0]))].sort();
  $("f-source").innerHTML =
    '<option value="">All sources</option>' + sources.map((s) => `<option>${esc(s)}</option>`).join("");
  if (sources.includes(current)) $("f-source").value = current;
}

function filtered() {
  const q = $("f-search").value.trim().toLowerCase();
  const source = $("f-source").value;
  const remote = $("f-remote").checked;
  const sort = $("f-sort").value;
  const skill = state.skillFilter;

  const out = state.jobs.filter((j) => {
    if (source && j.source.split(":")[0] !== source) return false;
    if (remote && !j.remote) return false;
    if (skill && !j.matched_skills.includes(skill)) return false;
    if (q) {
      const hay = `${j.title} ${j.company} ${j.location} ${j.description_snippet} ${j.matched_skills.join(" ")}`;
      if (!hay.toLowerCase().includes(q)) return false;
    }
    return true;
  });
  if (sort === "date") out.sort((a, b) => (b.posted_date || "").localeCompare(a.posted_date || ""));
  if (sort === "seen") out.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || b.score - a.score);
  return out;
}

function jobCard(j, maxScore) {
  const cls = scoreClass(j.score);
  const pct = Math.round((j.score / maxScore) * 100);
  const meta = [
    j.company && `<span>${esc(j.company)}</span>`,
    j.location && `<span>📍 ${esc(j.location)}</span>`,
    j.remote && `<span class="tag">Remote</span>`,
    j.remote && !j.remote_ok && `<span class="tag warn" title="Location names a region outside your remote regions">Region-locked?</span>`,
    j.salary && `<span>💰 ${esc(j.salary)}</span>`,
    j.years_required != null && `<span>${j.years_required}+ yrs</span>`,
    j.posted_date && `<span>Posted ${esc(j.posted_date)}</span>`,
    `<span>via ${esc(j.source)}</span>`,
  ].filter(Boolean).join("");
  const weights = state.applicant.skills || {};
  const skills = j.matched_skills.length
    ? j.matched_skills.map((s) =>
        `<button type="button" class="chip hit${s === state.skillFilter ? " active" : ""}" data-filter-skill="${esc(s)}" title="Show only jobs mentioning ${esc(s)}">${esc(s)}<b>+${weights[s] ?? ""}</b></button>`).join("")
    : '<span class="muted small">None of your skills mentioned</span>';

  return `
    <article class="job${j.eligible ? "" : " ineligible"}">
      <div class="rank">${j.eligible ? `#${j.rank}` : "–"}<small>${j.eligible ? "rank" : "no match"}</small></div>
      <div>
        <a class="job-title" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a>
        <div class="meta">${meta}</div>
        <div class="chips">${skills}</div>
        ${j.description_snippet ? `<p class="desc clamp" title="Click to expand">${esc(j.description_snippet)}</p>` : ""}
        ${j.eligible ? "" : `<div class="reasons">Not a match: ${esc(j.reasons.join("; "))}</div>`}
      </div>
      <div class="score">
        <div class="score-num s-${cls}">${j.score}</div>
        <div class="score-bar"><span class="bg-${cls}" style="width:${pct}%"></span></div>
        <small>match</small>
      </div>
    </article>`;
}

function render() {
  const shown = filtered();
  const maxScore = Math.max(1, ...state.jobs.map((j) => j.score));
  $("jobs").innerHTML = shown.map((j) => jobCard(j, maxScore)).join("");
  $("empty").hidden = shown.length > 0;
  $("empty").textContent = state.jobs.length
    ? "No jobs match these filters."
    : "No matching jobs yet. Try a longer \"Posted within\" window, lower the minimum score, or add skills and locations.";

  $("active-skill").hidden = !state.skillFilter;
  $("active-skill").innerHTML = state.skillFilter
    ? `Showing jobs that mention <b>${esc(state.skillFilter)}</b> <button type="button" class="btn ghost small-btn" id="clear-skill">Clear</button>`
    : "";

  const eligible = state.jobs.filter((j) => j.eligible).length;
  $("stats").textContent = `${eligible} jobs match your profile · showing ${shown.length}`;
}

["f-search", "f-source", "f-remote", "f-sort"].forEach((id) => $(id).addEventListener("input", render));
$("f-age").addEventListener("input", () => {
  loadJobs();
  // Remember the choice for next time (no re-rank needed, loadJobs already did it).
  const max_days_old = $("f-age").value === "" ? null : Number($("f-age").value);
  state.applicant.max_days_old = max_days_old;
  supabase.from("applicant").update({ max_days_old }).eq("user_id", state.user.id).then(() => {});
});
$("f-all").addEventListener("input", () => loadJobs());
$("jobs").addEventListener("click", (e) => {
  const skill = e.target.closest("[data-filter-skill]");
  if (skill) {
    state.skillFilter = state.skillFilter === skill.dataset.filterSkill ? null : skill.dataset.filterSkill;
    return render();
  }
  if (e.target.classList.contains("desc")) e.target.classList.toggle("clamp");
});
$("active-skill").addEventListener("click", (e) => {
  if (e.target.id === "clear-skill") {
    state.skillFilter = null;
    render();
  }
});

routeOnce().catch((err) => {
  $("stats").textContent = `Something went wrong: ${err.message}`;
});
