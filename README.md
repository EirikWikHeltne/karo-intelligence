# Karo Intelligence · Markedsintelligens

Automatisert nyhetsagent for Karo Healthcare Norway. Henter daglig nyheter fra norske og internasjonale kilder, klassifiserer dem med Claude AI, og presenterer dem i en intern webapp.

**Live:** [karo-intelligence.vercel.app](https://karo-intelligence.vercel.app)

---

## Hvordan det fungerer

```
RSS-feeds + målrettede Google News-søk (Karo-merker, apotek, konkurrenter)
       ↓
Relevans-filter: minst ett kjerne-ord, eller to kontekst-ord (hele ord, ikke delstrenger)
       ↓
Claude scorer Karo-relevans 0–100 etter fast rubrikk – kun score ≥ 65 lagres
(uten API: streng regelbasert score, kun saker med kjerne-treff lagres)
       ↓
Supabase (database)
       ↓
Vercel (webapp)
```

**Daglig** (man–fre kl. 07:00 og 13:00): GitHub Actions kjører `main.py` → nye artikler lagres i databasen → vises i appen umiddelbart.

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
├── index.html                   # Frontend (statisk, hostet på Vercel)
└── og-image.png                 # Open Graph-bilde for deling
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
2. La **Root Directory** stå som repo-roten
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

**Målrettede søk (Google News):** Karo/Decubal/Locobase/Apobase, Ibux/Paracet/reseptfritt, apotekkjedene, hud/tannhelse, Haleon/Kenvue/Beiersdorf/consumer health

**Norske nyheter (13):** VG, E24, NRK, Dagbladet, Aftenposten, Dagsavisen, DN, Finansavisen, Nettavisen, TV2, Dagens Medisin, Farmatid, Dagligvarehandelen

**Myndigheter (4):** FHI, SSB, DMP, Helsedirektoratet

**Internasjonale (3):** NYT, The Economist, Fierce Pharma – må alltid treffe et kjerne-ord

Kildeliste og relevans-ord i `index.html` speiler `main.py` – oppdater begge ved endring.

---

## Feilsøking

Agenten skriver tydelige feil i GitHub Actions-loggen, og kjøringen blir rød hvis ingenting kan lagres.

| Melding | Løsning |
|---------|---------|
| `Anthropic-kontoen er tom for kreditt` | Fyll på under Plans & Billing på console.anthropic.com. Til da brukes streng lokal klassifisering. |
| `SUPABASE_URL peker til en vert som ikke finnes` | Rett secreten `SUPABASE_URL` til `https://<prosjekt-id>.supabase.co` (samme prosjekt som i `index.html`). |
| `N kilder ga ingen data` | Feeden er nede eller har endret adresse – sjekk `[FEED]`-linjene. |
| Appen viser «Ingen nye saker siden …» | Agenten har ikke kjørt. GitHub skrur av planlagte workflows etter 60 dager uten aktivitet – aktiver under **Actions**. |

---

## Webapp-funksjoner

- **Dagens brief** – den mest Karo-relevante saken som toppsak + artikkelliste siste 24 timer
- **Kun sterke treff** – saker med score under 65 skjules som standard («Vis svake treff» viser alle)
- **Ukesdigest** – AI-generert oppsummering av ukens viktigste, vises øverst i Dagens brief i 7 dager (kan skjules)
- **Helg/stille dager** – finnes ingen saker siste 24 timer, vises de siste sakene i stedet for en tom side
- **Arkiv & søk** – fulltekstsøk, filtrering på kilde, kategori, merkevare og dato; «Last inn eldre saker» henter mer historikk
- **Karo brand-badge** – artikler som nevner Decubal, Locobase, Apobase eller Flux merkes automatisk
- **+ Legg til artikkel** – teamet kan manuelt legge inn URL-er direkte i appen
- **Tilbakemelding** – tommel opp/ned per artikkel for kalibrering av agenten
- **Mobil** – bunnnavigasjon optimert for iOS Safari
- **Mørkt tema** – følger systemet, kan byttes med ◐ i toppen
- **Snarveier** – `/` hopper til søk, `Esc` lukker dialoger; visningen ligger i URL-en (`#brief`, `#arkiv`, `#kilder`)

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
