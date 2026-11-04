-- First applicant: the profile that used to be hardcoded in config/config.json.
-- user_id is filled in by link_applicant_to_user() when this email signs in.
insert into public.applicant (
  email, name, headline, years_experience, target_roles, locations, open_to_remote,
  remote_allowed_regions, skills, title_include, title_exclude, max_years_required,
  min_score, max_days_old
) values (
  '16211a12b0@gmail.com',
  null,
  '~4 yrs. Targeting associate / mid-level Software Engineer roles (no senior+). Latest role CVS Health: Java, Node.js, GCP BigQuery, API extraction, Tableau. Earlier: Spring Boot, Angular, microservices.',
  4,
  array['Java Developer', 'Node.js Software Engineer', 'GCP BigQuery Data Engineer', 'Java Backend Engineer'],
  '[{"city": "Hyderabad", "country": "India", "country_code": "IN"}]',
  true,
  array['worldwide', 'anywhere', 'global', 'india', 'apac', 'asia'],
  '{"java": 3, "node.js": 3, "nodejs": 3, "node": 1, "bigquery": 3, "gcp": 3, "google cloud": 3,
    "spring boot": 3, "spring": 1, "microservices": 2, "rest": 1, "rest api": 1, "api": 1,
    "angular": 2, "typescript": 1, "javascript": 1, "express": 1, "etl": 2, "data pipeline": 2,
    "data pipelines": 2, "data engineering": 2, "tableau": 2, "sql": 1, "mysql": 1, "nosql": 1,
    "aws": 1, "ec2": 1, "jenkins": 1, "ci/cd": 1, "python": 1}',
  array['engineer', 'developer', 'sde', 'software', 'backend', 'back end', 'full stack',
        'fullstack', 'programmer', 'data', 'associate'],
  array['staff', 'principal', 'lead', 'manager', 'director', 'architect', 'head', 'vp', 'intern',
        'internship', 'sales', 'recruiter', 'ios', 'android', 'senior', 'sr', 'iii', 'iv', '3', '4',
        'smts', 'lmts', 'pmts'],
  4,
  4,
  5
)
on conflict (email) do nothing;
