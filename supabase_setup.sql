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

-- NB: service_role-nøkkelen (brukes av agenten i GitHub Actions) går utenom RLS og
-- trenger ingen policy. Policyene under gjelder anon-nøkkelen som webappen bruker.
-- Siden appen er intern og ikke har innlogging, har anon full tilgang – alle som har
-- adressen kan altså lese, endre og slette. Vurder innlogging (Supabase Auth) eller
-- passordbeskyttelse i Vercel hvis appen skal deles bredere.
-- (PostgreSQL støtter ikke CREATE POLICY IF NOT EXISTS, derfor DROP + CREATE.)
DROP POLICY IF EXISTS "Service role full access" ON articles;

DROP POLICY IF EXISTS "Anon read" ON articles;
CREATE POLICY "Anon read"   ON articles FOR SELECT USING (true);

DROP POLICY IF EXISTS "Anon insert" ON articles;
CREATE POLICY "Anon insert" ON articles FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "Anon update" ON articles;
CREATE POLICY "Anon update" ON articles FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Anon delete" ON articles;
CREATE POLICY "Anon delete" ON articles FOR DELETE USING (true);

-- ── Tilbakemeldinger (tommel opp/ned i webappen) ─────────────────────────────
-- Én stemme per artikkel, delt av hele teamet.
CREATE TABLE IF NOT EXISTS feedback (
  article_id  uuid        PRIMARY KEY REFERENCES articles (id) ON DELETE CASCADE,
  vote        text        NOT NULL CHECK (vote IN ('up', 'down')),
  voted_at    timestamptz DEFAULT now()
);

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anon read" ON feedback;
CREATE POLICY "Anon read"   ON feedback FOR SELECT USING (true);

DROP POLICY IF EXISTS "Anon insert" ON feedback;
CREATE POLICY "Anon insert" ON feedback FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "Anon update" ON feedback;
CREATE POLICY "Anon update" ON feedback FOR UPDATE USING (true) WITH CHECK (true);
