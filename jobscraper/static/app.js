import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from "./config.js";

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
const $ = (id) => document.getElementById(id);
const state = { user: null, applicant: null, jobs: [], loadedArgs: null };

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
const list = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

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
  // Default the age filter to the profile's preference.
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
  state.applicant = null;
  state.jobs = [];
  state.loadedArgs = null;
  routeOnce();
});

let routing = null;
function routeOnce() {
  routing ??= route().finally(() => (routing = null));
  return routing;
}

supabase.auth.onAuthStateChange((event) => {
  // SIGNED_IN fires after the magic link redirect; ignore token refreshes.
  // Deferred: calling Supabase inside this callback can deadlock supabase-js.
  if (event === "SIGNED_IN" && !state.user) setTimeout(routeOnce, 0);
});

// ---------------------------------------------------------------- resume upload

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("upload-file").files[0];
  if (!file) return;
  const ext = file.name.toLowerCase().endsWith(".pdf") ? "pdf" : file.name.toLowerCase().endsWith(".txt") ? "txt" : null;
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
    await showMatches();
  } catch (err) {
    $("upload-msg").textContent = `Failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

$("replace-btn").addEventListener("click", () => showUpload(true));
$("upload-cancel").addEventListener("click", () => showMatches());

// ---------------------------------------------------------------- profile

function renderProfile() {
  const a = state.applicant;
  $("profile-name").textContent = a.name || "Your profile";
  $("profile-summary").textContent = a.headline || "";
  const places = (a.locations || []).map((p) => p.city || p.country).filter(Boolean);
  const facts = [
    ["Target roles", (a.target_roles || []).join(", ") || "—"],
    ["Locations", [...places, a.open_to_remote ? "Remote" : null].filter(Boolean).join(", ") || "Any"],
    ["Experience", a.years_experience != null ? `${+a.years_experience} yrs` : "—"],
    ["Max years asked", a.max_years_required ?? "No limit"],
    ["Min score", a.min_score],
    ["Excludes", (a.title_exclude || []).filter((t) => t.length > 2).slice(0, 6).join(", ") || "—"],
  ];
  $("profile-facts").innerHTML = facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  $("profile-skills").innerHTML = Object.entries(a.skills || {})
    .sort((x, y) => y[1] - x[1])
    .map(([s, w]) => `<span class="chip">${esc(s)}<b>${w}</b></span>`)
    .join("");
}

$("edit-btn").addEventListener("click", () => {
  const a = state.applicant;
  const f = $("edit-form").elements;
  f.name.value = a.name ?? "";
  f.target_roles.value = (a.target_roles || []).join(", ");
  f.locations.value = (a.locations || []).map((p) => [p.city, p.country, p.country_code].filter(Boolean).join(", ")).join("\n");
  f.open_to_remote.checked = !!a.open_to_remote;
  f.remote_allowed_regions.value = (a.remote_allowed_regions || []).join(", ");
  f.skills.value = Object.entries(a.skills || {}).sort((x, y) => y[1] - x[1]).map(([s, w]) => `${s}:${w}`).join(", ");
  f.title_include.value = (a.title_include || []).join(", ");
  f.title_exclude.value = (a.title_exclude || []).join(", ");
  f.max_years_required.value = a.max_years_required ?? "";
  f.min_score.value = a.min_score ?? 1;
  $("edit-msg").textContent = "";
  $("edit-dialog").showModal();
});

function readProfileForm() {
  const f = $("edit-form").elements;
  const skills = {};
  for (const part of list(f.skills.value)) {
    const [name, weight] = part.split(":").map((x) => x.trim());
    const w = Number(weight ?? 1);
    if (!name || !Number.isInteger(w) || w < 1 || w > 3) throw new Error(`Bad skill entry "${part}" (use skill:1, skill:2 or skill:3)`);
    skills[name.toLowerCase()] = w;
  }
  const locations = f.locations.value.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
    const [city = "", country = "", code = ""] = line.split(",").map((x) => x.trim());
    return { city, country, country_code: code.toUpperCase() };
  });
  return {
    name: f.name.value.trim() || null,
    target_roles: list(f.target_roles.value),
    locations,
    open_to_remote: f.open_to_remote.checked,
    remote_allowed_regions: list(f.remote_allowed_regions.value.toLowerCase()),
    skills,
    title_include: list(f.title_include.value.toLowerCase()),
    title_exclude: list(f.title_exclude.value.toLowerCase()),
    max_years_required: f.max_years_required.value === "" ? null : Number(f.max_years_required.value),
    min_score: Math.max(1, Number(f.min_score.value) || 1),
  };
}

$("edit-form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "save") return; // Cancel closes the dialog
  e.preventDefault();
  let changes;
  try {
    changes = readProfileForm();
  } catch (err) {
    return ($("edit-msg").textContent = err.message);
  }
  const { data, error } = await supabase.from("applicant").update(changes)
    .eq("user_id", state.user.id).select().single();
  if (error) return ($("edit-msg").textContent = `Save failed: ${error.message}`);
  state.applicant = data;
  $("edit-dialog").close();
  renderProfile();
  await loadJobs(true);
});

// ---------------------------------------------------------------- jobs

async function loadJobs(force = false) {
  const age = $("f-age").value;
  const args = {
    p_max_days: age === "" ? null : Number(age),
    p_include_ineligible: $("f-all").checked,
    p_limit: 500,
  };
  const key = JSON.stringify(args);
  if (!force && key === state.loadedArgs) return render();
  $("stats").textContent = "Matching jobs to your profile…";
  const { data, error } = await supabase.rpc("match_jobs", args);
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
  $("f-min").max = Math.max(1, ...state.jobs.map((j) => j.score));
}

function filtered() {
  const q = $("f-search").value.trim().toLowerCase();
  const source = $("f-source").value;
  const min = +$("f-min").value;
  const remote = $("f-remote").checked;
  const sort = $("f-sort").value;

  const out = state.jobs.filter((j) => {
    if (source && j.source.split(":")[0] !== source) return false;
    if (j.score < min) return false;
    if (remote && !j.remote) return false;
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
    ? j.matched_skills.map((s) => `<span class="chip hit">${esc(s)}<b>+${weights[s] ?? ""}</b></span>`).join("")
    : '<span class="muted small">None of your skills mentioned</span>';

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
  const shown = filtered();
  const maxScore = Math.max(1, ...state.jobs.map((j) => j.score));
  $("jobs").innerHTML = shown.map((j) => jobCard(j, maxScore)).join("");
  $("empty").hidden = shown.length > 0;
  $("empty").textContent = state.jobs.length
    ? "No jobs match these filters."
    : "No matching jobs yet. Try a longer \"Posted within\" window, or check back after the next daily scrape.";

  const eligible = state.jobs.filter((j) => j.eligible).length;
  const capped = state.jobs.length >= 500 ? " (top 500)" : "";
  $("stats").textContent = `${eligible} jobs fit your profile${capped} · showing ${shown.length}`;
}

["f-search", "f-source", "f-min", "f-remote", "f-sort"].forEach((id) => $(id).addEventListener("input", render));
["f-age", "f-all"].forEach((id) => $(id).addEventListener("input", () => loadJobs()));
$("jobs").addEventListener("click", (e) => {
  if (e.target.classList.contains("desc")) e.target.classList.toggle("clamp");
});

routeOnce().catch((err) => {
  $("stats").textContent = `Something went wrong: ${err.message}`;
});
