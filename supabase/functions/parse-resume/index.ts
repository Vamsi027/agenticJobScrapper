// parse-resume: turns the signed-in user's uploaded resume into their applicant row.
//
// Flow: the browser uploads the file to storage at resumes/<user id>/resume.<ext>,
// then POSTs {"path": "<user id>/resume.<ext>"} here with the user's session.
// This function checks who is calling, sends the file to Claude, and upserts
// public.applicant (user_id, email and the parsed profile).
//
// Secrets: ANTHROPIC_API_KEY (set with `supabase secrets set` or in the dashboard).
// SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY are provided by the platform.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Anthropic from "npm:@anthropic-ai/sdk";
import { createClient } from "npm:@supabase/supabase-js@2";
import { encodeBase64 } from "jsr:@std/encoding/base64";

const MODEL = "claude-opus-5-5";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

// Structured output: every field required, no extras (structured-output rules).
const PROFILE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "name", "headline", "years_experience", "target_roles", "locations", "open_to_remote",
    "remote_allowed_regions", "skills", "title_include", "title_exclude",
    "max_years_required", "min_score",
  ],
  properties: {
    name: { type: "string" },
    headline: { type: "string" },
    years_experience: { type: "number" },
    target_roles: { type: "array", items: { type: "string" } },
    locations: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["city", "country", "country_code"],
        properties: {
          city: { type: "string" },
          country: { type: "string" },
          country_code: { type: "string" },
        },
      },
    },
    open_to_remote: { type: "boolean" },
    remote_allowed_regions: { type: "array", items: { type: "string" } },
    skills: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["skill", "weight"],
        properties: {
          skill: { type: "string" },
          weight: { type: "integer", enum: [1, 2, 3] },
        },
      },
    },
    title_include: { type: "array", items: { type: "string" } },
    title_exclude: { type: "array", items: { type: "string" } },
    max_years_required: { type: "integer" },
    min_score: { type: "integer" },
  },
};

const SYSTEM = `You read a job seeker's resume and produce the profile a job-matching system uses to find and rank postings for them. Postings are matched by whole-word, case-insensitive search of the posting title and description, so every term you output must be a word or phrase that literally appears in real job postings.

Fields:
- name: the candidate's name as written.
- headline: one sentence: years of experience, the level they should target, their most recent role and its main technologies.
- years_experience: total professional experience in years (decimals allowed). Exclude internships and education.
- target_roles: 3-5 job titles to search job boards for, at the level they should apply to now (e.g. "Backend Engineer", "Data Engineer"), most suitable first.
- locations: where they want to work. Use the resume's stated preference; otherwise their current city. country_code is ISO 3166-1 alpha-2.
- open_to_remote: true unless the resume says they want on-site only.
- remote_allowed_regions: lowercase words a remote posting's location could use that would include this candidate: always "worldwide", "anywhere", "global", plus their country names and regions (e.g. "india", "apac", "asia", or "usa", "united states", "north america").
- skills: 15-35 lowercase skills, tools and domains from the resume. weight 3 = core skill from recent work, 2 = solid working experience, 1 = familiar or older. Add common spelling variants as separate entries with the same weight (e.g. "node.js" and "nodejs"; "gcp" and "google cloud"). Skip soft skills.
- title_include: lowercase words, at least one of which a suitable posting title contains (e.g. "engineer", "developer", "software", "data", "analyst"). Broad enough not to miss suitable roles.
- title_exclude: lowercase words that mark a title as wrong for them: seniority levels above their experience (e.g. "senior", "sr", "staff", "principal", "lead", "manager", "director", "architect", "head", "vp", and level numerals like "iii" when they are mid-level), internships if they are experienced, and unrelated functions (e.g. "sales", "recruiter"). Never include a word that also appears in target_roles.
- max_years_required: the most years of experience a posting can ask for and still be realistic for them: their years of experience rounded, plus 1 if they are strong for their level.
- min_score: the minimum sum of matched skill weights for a posting to count as relevant; usually 3-5.`;

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const url = Deno.env.get("SUPABASE_URL")!;
  const authHeader = req.headers.get("Authorization") ?? "";

  // Who is calling? Verified against Supabase Auth with the caller's own token.
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authHeader } },
  });
  const { data: { user }, error: authError } = await asUser.auth.getUser(authHeader.replace(/^Bearer\s+/i, ""));
  if (authError || !user) return json({ error: "Sign in first." }, 401);

  const { path } = await req.json().catch(() => ({}));
  if (typeof path !== "string" || !path.startsWith(`${user.id}/`)) {
    return json({ error: "Upload the resume to your own folder first." }, 400);
  }

  // Read the file as the user, so storage RLS still applies.
  const { data: file, error: dlError } = await asUser.storage.from("resumes").download(path);
  if (dlError || !file) return json({ error: `Could not read the uploaded resume: ${dlError?.message}` }, 400);

  const isPdf = path.toLowerCase().endsWith(".pdf");
  const document = isPdf
    ? { type: "document" as const, source: { type: "base64" as const, media_type: "application/pdf" as const, data: encodeBase64(new Uint8Array(await file.arrayBuffer())) } }
    : { type: "document" as const, source: { type: "text" as const, media_type: "text/plain" as const, data: await file.text() } };

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY secret is not set");
    return json({ error: "Resume parsing isn't configured yet (missing Claude API key)." }, 503);
  }

  let profile;
  try {
    const anthropic = new Anthropic({ apiKey });
    const response = await anthropic.beta.messages.create({
      model: MODEL,
      max_tokens: 16000,
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      system: SYSTEM,
      output_config: { effort: "medium", format: { type: "json_schema", schema: PROFILE_SCHEMA } },
      messages: [{ role: "user", content: [document, { type: "text", text: "Build the profile for this resume." }] }],
    } as any);

    if (response.stop_reason === "refusal") {
      return json({ error: "The resume could not be processed. Try a different file." }, 422);
    }
    if (response.stop_reason === "max_tokens") {
      return json({ error: "The resume was too long to process." }, 422);
    }
    const text = response.content.find((b: { type: string }) => b.type === "text") as { text: string } | undefined;
    profile = JSON.parse(text?.text ?? "");
  } catch (err) {
    if (err instanceof Anthropic.APIError) {
      console.error("Claude API error", err.status, err.message);
      return json({ error: "Resume parsing is unavailable right now. Try again in a minute." }, 502);
    }
    console.error("Resume parsing failed", err);
    return json({ error: "Resume parsing failed." }, 500);
  }

  const lower = (xs: string[]) => [...new Set(xs.map((x) => x.trim().toLowerCase()).filter(Boolean))];
  const row = {
    user_id: user.id,
    email: user.email?.toLowerCase() ?? null,
    name: profile.name || null,
    headline: profile.headline,
    years_experience: profile.years_experience,
    target_roles: profile.target_roles,
    locations: profile.locations,
    open_to_remote: profile.open_to_remote,
    remote_allowed_regions: lower(profile.remote_allowed_regions),
    skills: Object.fromEntries(profile.skills.map((s: { skill: string; weight: number }) => [s.skill.trim().toLowerCase(), s.weight])),
    title_include: lower(profile.title_include),
    title_exclude: lower(profile.title_exclude),
    max_years_required: profile.max_years_required,
    min_score: Math.max(1, profile.min_score),
    resume_path: path,
    resume_parsed_at: new Date().toISOString(),
  };

  // Writes use the service role: users can't set user_id/email themselves.
  const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  // Claim a pre-seeded row with this email if the sign-up trigger didn't.
  if (user.email) {
    await admin.from("applicant").update({ user_id: user.id }).is("user_id", null).eq("email", user.email.toLowerCase());
  }
  const { data: saved, error: saveError } = await admin
    .from("applicant").upsert(row, { onConflict: "user_id" }).select().single();
  if (saveError) {
    console.error("Saving applicant failed", saveError);
    return json({ error: `Saving your profile failed: ${saveError.message}` }, 500);
  }
  return json({ applicant: saved });
});
