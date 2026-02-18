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
  relevance_score  int,
  created_at       timestamptz DEFAULT now()
);

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
