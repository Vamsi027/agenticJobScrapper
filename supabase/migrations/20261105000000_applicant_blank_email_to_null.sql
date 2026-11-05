-- Guests (anonymous sign-ins) have no email; Supabase reports it as "".
-- Store blanks as NULL so the unique email index doesn't collide between guests.
update public.applicant set email = null where email = '';

create or replace function public.applicant_normalize_email()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.email := nullif(lower(btrim(new.email)), '');
  return new;
end $$;
create trigger applicant_normalize_email before insert or update of email on public.applicant
  for each row execute function public.applicant_normalize_email();
