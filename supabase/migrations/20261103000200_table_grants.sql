-- This project does not auto-grant Data API privileges on new tables, so grant
-- exactly what each role needs. Row-level security still limits which rows.
grant select on public.job_postings to anon, authenticated;
grant select, insert, update, delete on public.job_postings to service_role;

grant select, delete on public.applicant to authenticated;   -- column-level UPDATE granted earlier
grant select, insert, update, delete on public.applicant to service_role;

-- TRUNCATE bypasses row-level security; browser roles never need it.
revoke truncate on public.job_postings, public.applicant from anon, authenticated;
