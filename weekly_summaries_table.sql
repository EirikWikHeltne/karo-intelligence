-- Kjør denne i Supabase SQL Editor

create table if not exists weekly_summaries (
  id            bigint generated always as identity primary key,
  title         text not null,
  summary       text not null,
  article_count int  default 0,
  week_start    date,
  created_at    timestamptz default now()
);

-- Tillat anon-lesing (for webapp)
alter table weekly_summaries enable row level security;

create policy "Public read" on weekly_summaries
  for select using (true);

-- Tillat service_role å skrive (GitHub Actions bruker SUPABASE_KEY = service_role)
create policy "Service write" on weekly_summaries
  for insert with check (true);
