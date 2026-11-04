-- HN posts without a "Company | Role | Location" header were stored with an
-- empty location, which made "Remote - US Only" posts look open to everyone.
-- The scraper now keeps the header line as the location; fix stored rows the same way.
update public.job_postings
   set location = title,
       dedupe_key = lower(company || '|' || title || '|' || title)
 where source = 'hn' and coalesce(location, '') = '';

-- Show all matching jobs by default, not just the last week's.
alter table public.applicant alter column max_days_old set default null;
update public.applicant set max_days_old = null where email = '16211a12b0@gmail.com';
