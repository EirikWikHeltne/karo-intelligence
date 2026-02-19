# Karo Intelligence · Markedsintelligens

Automatisert nyhetsagent for Karo Healthcare Norway. Henter daglig nyheter fra norske og internasjonale kilder, klassifiserer dem med Claude AI, og presenterer dem i en intern webapp.

**Live:** [karo-intelligence.vercel.app](https://karo-intelligence.vercel.app)

---

## Hvordan det fungerer

```
RSS-feeds (14 kilder)
       ↓
Nøkkelord-filter (~110 ord)
       ↓
Claude klassifiserer relevans + kategori + sammendrag
       ↓
Supabase (database)
       ↓
Vercel (webapp)
```

**Daglig** (man–fre kl. 07:00): GitHub Actions kjører `main.py` → nye artikler lagres i databasen → vises i appen umiddelbart.

**Ukentlig** (fre kl. 08:00): `weekly_digest.py` genererer en AI-oppsummering av ukens viktigste saker → vises som banner øverst i appen.

---

## Filstruktur

```
├── main.py                      # Daglig nyhetsagent
├── weekly_digest.py             # Fredag-digest (AI-oppsummering)
├── requirements.txt             # Python-avhengigheter
├── supabase_setup.sql           # Database-tabell: articles
├── weekly_summaries_table.sql   # Database-tabell: weekly_summaries
├── .github/
│   └── workflows/
│       └── pharma-news.yml      # GitHub Actions (daglig + ukentlig)
└── webapp/
    ├── index.html               # Frontend (statisk, hostet på Vercel)
    └── og-image.png             # Open Graph-bilde for deling
```

---

## Oppsett (første gang)

### 1. Klone og installere

```bash
git clone https://github.com/EirikWikHeltne/karo-intelligence.git
cd karo-intelligence
pip install -r requirements.txt
```

### 2. Supabase

1. Opprett et nytt prosjekt på [supabase.com](https://supabase.com)
2. Gå til **SQL Editor** og kjør begge SQL-filene:
   - `supabase_setup.sql` (articles-tabell)
   - `weekly_summaries_table.sql` (ukesdigest-tabell)
3. Hent `Project URL` og `service_role key` under **Settings → API**

### 3. GitHub Secrets

Legg inn følgende under **Settings → Secrets → Actions** i GitHub-repoet:

| Secret | Verdi |
|--------|-------|
| `ANTHROPIC_API_KEY` | API-nøkkel fra [console.anthropic.com](https://console.anthropic.com) |
| `SUPABASE_URL` | Project URL fra Supabase |
| `SUPABASE_KEY` | `service_role` key fra Supabase |

### 4. Vercel

1. Importer repoet på [vercel.com](https://vercel.com)
2. Sett **Root Directory** til `webapp`
3. Ingen build-kommando trengs – det er en statisk HTML-fil

---

## Kjøre manuelt

**Nyhetsagent:**
```bash
export ANTHROPIC_API_KEY=...
export SUPABASE_URL=...
export SUPABASE_KEY=...
python main.py
```

**Ukesdigest:**
```bash
python weekly_digest.py
```

**Via GitHub Actions UI:**
Gå til **Actions → Pharma News Agent → Run workflow**. Du kan velge å kjøre ukesdigesten manuelt ved å sette `run_digest = true`.

---

## Kategorier

| Kategori | Beskrivelse |
|----------|-------------|
| `M&A` | Oppkjøp, fusjoner, PE-aktivitet |
| `apotek` | Apotek 1, Vitusapotek, Boots, apotekbransjen |
| `dagligvare` | Rema, NorgesGruppen, Coop, hylleplass |
| `dermatologi` | Eksem, psoriasis, barrierekrem, hudpleie |
| `oral-care` | Tannpleie, munnvann, Colgate, Oral-B |
| `konkurrenter` | Beiersdorf, Eucerin, Unilever, L'Oréal |
| `regulatorisk` | Legemiddelverket, EU-regulering, reseptfrihet |
| `forbrukertrender` | Forbrukervaner, prisvekst, selvmedisinering |
| `helsepolitikk` | FHI, folkehelse, pilleforbruk |
| `markedsføring` | Influencer, sosiale medier, digital markedsføring |
| `økonomi` | Inflasjon, kronekurs, makro |

---

## Kilder

**Norske (11):** VG, E24, NRK, Dagbladet, Aftenposten, Dagsavisen, DN, Finansavisen, Nettavisen, TV2, Dagens Medisin

**Internasjonale (3):** Reuters, NYT, The Economist

---

## Webapp-funksjoner

- **Dagens brief** – toppsak med bilde + artikelliste siste 24 timer
- **Ukesdigest** – AI-generert oppsummering av ukens viktigste (vises fredag)
- **Arkiv & søk** – fulltekstsøk, filtrering på kilde og kategori
- **Karo brand-badge** – artikler som nevner Decubal, Locobase, Apobase eller Flux merkes automatisk
- **+ Legg til artikkel** – teamet kan manuelt legge inn URL-er direkte i appen
- **Tilbakemelding** – tommel opp/ned per artikkel for kalibrering av agenten
- **Mobil** – bunnnavigasjon optimert for iOS Safari

---

## Teknisk stack

| Komponent | Teknologi |
|-----------|-----------|
| Nyhetsagent | Python 3.12 |
| AI-klassifisering | Claude Haiku (Anthropic) |
| Scheduler | GitHub Actions |
| Database | Supabase (PostgreSQL) |
| Frontend | Vanilla HTML/CSS/JS |
| Hosting | Vercel |

---

*Intern bruk · Karo Healthcare Norway · Ikke for distribusjon*
