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

drop policy if exists "Public read" on weekly_summaries;
create policy "Public read" on weekly_summaries
  for select using (true);

-- Skriving gjøres av GitHub Actions med service_role-nøkkelen, som går utenom RLS.
-- Det skal derfor ikke finnes noen insert-policy her (den ville gitt anon skrivetilgang).
drop policy if exists "Service write" on weekly_summaries;
