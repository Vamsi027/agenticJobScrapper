-- Matching no longer excludes jobs by title words (senior, lead, ...): every
-- posting that matches a user's roles, skills, years and locations is shown.
-- Also: no row cap by default, so users see all their matches.

create or replace function public.match_jobs(
  p_max_days int default null,
  p_include_ineligible boolean default false,
  p_limit int default null)
returns table (
  id bigint, title text, company text, location text, remote boolean, salary text, url text,
  description_snippet text, posted_date date, first_seen timestamptz, source text,
  years_required smallint, score int, matched_skills text[], remote_ok boolean,
  eligible boolean, reasons text[])
language sql stable security invoker set search_path = '' as $$
with me as (
  select * from public.applicant where user_id = (select auth.uid())
),
skills as (
  select s.key as skill, s.value::int as weight, public.term_pattern(s.key) as pat
  from me, jsonb_each_text(me.skills) s
),
cities as (
  select lower(p->>'city') as city
  from me, jsonb_array_elements(me.locations) p
  where coalesce(p->>'city', '') <> ''
),
scored as (
  select j.*, me.title_include, me.max_years_required, me.min_score,
         me.open_to_remote, jsonb_array_length(me.locations) as n_locations,
         sk.score, sk.matched,
         exists (select 1 from unnest(me.title_include) x
                  where lower(j.title) ~ public.term_pattern(x)) as include_hit,
         j.remote and (
           exists (select 1 from unnest(me.remote_allowed_regions) r
                    where lower(coalesce(j.location, '')) ~ public.term_pattern(r))
           -- "Remote" with no place named counts as open to anyone
           or regexp_replace(lower(coalesce(j.location, '')), '\mremote\M|[^a-z]', '', 'g') = ''
         ) as remote_ok,
         exists (select 1 from cities c
                  where lower(coalesce(j.location, '')) like '%' || c.city || '%') as in_city
  from public.job_postings j
  cross join me
  cross join lateral (
    select coalesce(sum(s.weight), 0)::int as score,
           coalesce(array_agg(s.skill order by s.weight desc, s.skill), '{}') as matched
    from skills s
    where lower(j.title || ' ' || coalesce(j.description, '')) ~ s.pat
  ) sk
  where p_max_days is null
     or coalesce(j.posted_date, (j.created_at at time zone 'utc')::date) >= current_date - p_max_days
),
evaluated as (
  select s.*,
    array_remove(array[
      case when cardinality(s.title_include) > 0 and not s.include_hit
           then 'title is not one of your target roles' end,
      case when s.max_years_required is not null and s.years_required > s.max_years_required
           then format('asks for %s+ years', s.years_required) end,
      case when s.score < s.min_score
           then format('score below %s', s.min_score) end,
      case when not ((s.n_locations = 0 and not s.open_to_remote) or s.in_city
                     or (s.open_to_remote and s.remote_ok))
           then 'outside your locations' end
    ], null) as why
  from scored s
)
select e.id, e.title, e.company, e.location, e.remote, e.salary, e.url,
       left(e.description, 600), e.posted_date, e.created_at, e.source, e.years_required,
       e.score, e.matched, e.remote_ok, cardinality(e.why) = 0, e.why
from evaluated e
where p_include_ineligible or cardinality(e.why) = 0
order by cardinality(e.why) = 0 desc, e.score desc,
         coalesce(e.posted_date, (e.created_at at time zone 'utc')::date) desc
limit p_limit
$$;

-- applicant.title_exclude is now unused (nothing reads or writes it). Drop it
-- when convenient: alter table public.applicant drop column title_exclude;
