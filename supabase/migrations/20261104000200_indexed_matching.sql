-- Fast, indexed skill matching.
--
-- Regex-matching every skill against every full description took ~14 s for
-- 3.9k postings, over the 8 s statement timeout for signed-in users. Postings
-- now carry a full-text vector of their normalized text, and each skill is one
-- GIN index lookup (phrase query), so matching takes ~0.1 s and grows with the
-- number of matching jobs, not the size of the table.
--
-- (While developing this, a "terms text" generated column was added to
-- job_postings and is no longer used: alter table public.job_postings drop column terms;)

-- Normalized text: lowercase; everything except letters, digits, + # and
-- in-word dots becomes a space ("Node.js, CI/CD" -> " node.js ci cd ").
create or replace function public.norm_terms(t text)
returns text language sql immutable parallel safe set search_path = '' as $$
  select ' ' || btrim(regexp_replace(regexp_replace(regexp_replace(
           lower(coalesce(t, '')),
           '[^a-z0-9+#.]+', ' ', 'g'),
           '(^| )\.+|\.+( |$)', '\1 \2', 'g'),
           ' +', ' ', 'g')) || ' '
$$;

-- Same, with the symbols that matter spelled out so the full-text parser keeps
-- "node.js", "c++" and "c#" as single words.
create or replace function public.ts_terms(t text)
returns text language sql immutable parallel safe set search_path = '' as $$
  select replace(replace(replace(public.norm_terms(t), '.', 'dot'), '+', 'plus'), '#', 'sharp')
$$;

-- Phrase query for one skill / title word, e.g. 'spring <-> boot'. NULL if empty.
create or replace function public.term_query(term text)
returns tsquery language sql immutable parallel safe set search_path = '' as $$
  select nullif(phraseto_tsquery('simple', public.ts_terms(term)), ''::tsquery)
$$;

alter table public.job_postings
  add column tsv tsvector generated always as
    (to_tsvector('simple', public.ts_terms(title || ' ' || coalesce(description, '')))) stored,
  add column title_tsv tsvector generated always as
    (to_tsvector('simple', public.ts_terms(title))) stored;
create index job_postings_tsv_idx on public.job_postings using gin (tsv);

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
with me as materialized (
  select * from public.applicant where user_id = (select auth.uid())
),
skills as materialized (
  select s.key as skill, s.value::int as weight, public.term_query(s.key) as q
  from me, jsonb_each_text(me.skills) s
  where public.term_query(s.key) is not null
),
includes as materialized (
  select public.term_query(x) as q from me, unnest(me.title_include) x
  where public.term_query(x) is not null
),
regions as materialized (
  select public.term_pattern(r) as pat from me, unnest(me.remote_allowed_regions) r
),
cities as materialized (
  select lower(p->>'city') as city
  from me, jsonb_array_elements(me.locations) p
  where coalesce(p->>'city', '') <> ''
),
-- One index lookup per skill; sum the weights per job.
hits as (
  select j.id, sum(s.weight)::int as score,
         array_agg(s.skill order by s.weight desc, s.skill) as matched
  from skills s
  join public.job_postings j on j.tsv @@ s.q
  group by j.id
),
-- Everything except the (large) description, which is read only for returned rows.
scored as (
  select j.id, j.location, j.remote, j.posted_date, j.created_at, j.years_required,
         me.max_years_required, me.min_score, me.open_to_remote,
         jsonb_array_length(me.locations) as n_locations,
         coalesce(h.score, 0) as score, coalesce(h.matched, '{}') as matched,
         (not exists (select 1 from includes)
          or exists (select 1 from includes i where j.title_tsv @@ i.q)) as include_ok,
         case when j.remote then
           exists (select 1 from regions r where lower(coalesce(j.location, '')) ~ r.pat)
           -- "Remote" with no place named counts as open to anyone
           or regexp_replace(lower(coalesce(j.location, '')), '\mremote\M|[^a-z]', '', 'g') = ''
         else false end as remote_ok,
         exists (select 1 from cities c
                  where lower(coalesce(j.location, '')) like '%' || c.city || '%') as in_city
  from public.job_postings j
  cross join me
  left join hits h on h.id = j.id
  where p_max_days is null
     or coalesce(j.posted_date, (j.created_at at time zone 'utc')::date) >= current_date - p_max_days
),
evaluated as (
  select s.*,
    array_remove(array[
      case when not s.include_ok then 'title is not one of your target roles' end,
      case when s.max_years_required is not null and s.years_required > s.max_years_required
           then format('asks for %s+ years', s.years_required) end,
      case when s.score < s.min_score
           then format('score below %s', s.min_score) end,
      case when not ((s.n_locations = 0 and not s.open_to_remote) or s.in_city
                     or (s.open_to_remote and s.remote_ok))
           then 'outside your locations' end
    ], null) as why
  from scored s
),
picked as (
  select e.*, cardinality(e.why) = 0 as fits,
         coalesce(e.posted_date, (e.created_at at time zone 'utc')::date) as sort_date
  from evaluated e
  where p_include_ineligible or cardinality(e.why) = 0
  order by cardinality(e.why) = 0 desc, e.score desc, sort_date desc
  limit p_limit
)
select p.id, j.title, j.company, j.location, j.remote, j.salary, j.url,
       left(j.description, 600), j.posted_date, j.created_at, j.source, j.years_required,
       p.score, p.matched, p.remote_ok, p.fits, p.why
from picked p
join public.job_postings j on j.id = p.id
order by p.fits desc, p.score desc, p.sort_date desc
$$;
