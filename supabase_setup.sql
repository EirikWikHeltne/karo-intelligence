-- Kjør dette i Supabase SQL Editor under Database > SQL Editor

CREATE TABLE IF NOT EXISTS articles (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  title            text        NOT NULL,
  url              text        UNIQUE NOT NULL,
  source           text        NOT NULL,
  published_at     timestamptz,
  ingress          text,
  summary          text,
  category         text,
  brand            text,
  relevance_score  int,
  created_at       timestamptz DEFAULT now()
);

-- Kjør dette hvis tabellen allerede finnes (migrering):
-- ALTER TABLE articles ADD COLUMN IF NOT EXISTS brand text;

-- Indekser for rask filtrering i arkivet
CREATE INDEX IF NOT EXISTS idx_articles_category     ON articles (category);
CREATE INDEX IF NOT EXISTS idx_articles_source       ON articles (source);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_created_at   ON articles (created_at DESC);

-- Aktiver Row Level Security (anbefalt for Supabase)
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;

-- Tillat lese- og skrivetilgang med service role key (brukes av agenten)
CREATE POLICY "Service role full access"
  ON articles
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Tillat oppdatering og sletting fra webapp (anon-nøkkel)
-- NB: Siden appen er intern og ikke har innlogging, gir vi anon tilgang.
-- Vurder å bytte til auth-basert tilgang hvis appen blir offentlig.
CREATE POLICY IF NOT EXISTS "Anon update"
  ON articles FOR UPDATE USING (true) WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Anon delete"
  ON articles FOR DELETE USING (true);

-- Tillat anon å lese (for webapp)
CREATE POLICY IF NOT EXISTS "Anon read"
  ON articles FOR SELECT USING (true);

-- Tillat anon å skrive (for manuell innsending)
CREATE POLICY IF NOT EXISTS "Anon insert"
  ON articles FOR INSERT WITH CHECK (true);
