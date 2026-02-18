"""
Pharma News Agent – Karo Healthcare
Henter RSS-feeds daglig, klassifiserer med Claude API,
og lagrer relevante artikler i Supabase.
"""

import os
import json
import feedparser
import anthropic
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


# ── Konfigurasjon ─────────────────────────────────────────────────────────────

RSS_FEEDS = {
    "VG":           ["https://www.vg.no/rss/feed/forsiden/",
                     "https://www.vg.no/rss/feed/?categories=1069"],
    "E24":          ["http://e24.no/rss2/",
                     "https://e24.no/rss2/?seksjon=boers-og-finans"],
    "NRK":          ["https://www.nrk.no/toppsaker.rss",
                     "https://www.nrk.no/norge/toppsaker.rss"],
    "Dagbladet":    ["https://www.dagbladet.no/?lab_viewport=rss"],
    "Aftenposten":  ["https://www.aftenposten.no/rss/"],
    "Dagsavisen":   ["https://www.dagsavisen.no/rss"],
    "DN":           ["https://services.dn.no/api/feed/rss/"],
    "Finansavisen": ["https://ws.finansavisen.no/api/articles.rss",
                     "https://ws.finansavisen.no/api/articles.rss?category=B%C3%B8rs"],
    "Nettavisen":   ["https://www.nettavisen.no/service/rich-rss?tag=nyheter"],
    "TV2":          ["https://www.tv2.no/rss/nyheter/innenriks",
                     "https://www.tv2.no/rss/nyheter/utenriks"],
}

KEYWORDS = [
    # Karo-merker (alltid relevant)
    "Decubal", "Locobase", "Apobase", "Flux",

    # Hudpleie / dermatologi
    "hudpleie", "eksem", "psoriasis", "atopisk", "barrierekrem",
    "dermatologi", "hudsykdom", "fuktighetskrem", "sårpleie",
    "tørr hud", "sensitiv hud", "kløe", "allergisk",

    # Oral care
    "tannpleie", "munnhygiene", "tannkrem", "munnvann",
    "tannhelse", "karies", "fluor", "tannlege",

    # Apotek
    "apotek", "Apotek 1", "Vitusapotek", "Boots",
    "Apotekforeningen", "apotekbransjen",

    # Dagligvare & retail
    "Rema 1000", "NorgesGruppen", "Coop", "Kiwi", "Meny", "Spar",
    "dagligvare", "hylleplass", "sortiment", "dagligvarebransjen",
    "supermarked", "matpris", "dagligvarekjede",

    # OTC / reseptfritt
    "OTC", "reseptfri", "reseptfritt", "egenpris",

    # Konkurrenter og brands
    "Beiersdorf", "Eucerin", "Nivea", "Unilever", "Vaseline",
    "La Roche-Posay", "Colgate", "Oral-B", "Sensodyne",
    "CeraVe", "Dove", "Johnson & Johnson", "Procter & Gamble",
    "L'Oréal", "Loreal",

    # M&A & PE – bredt
    "oppkjøp", "fusjon", "oppkjøpet", "kjøper opp",
    "private equity", "KKR", "Nordic Capital", "EQT",
    "Axel Johnson", "Orkla", "Schibsted",
    "consumer health", "konsumenthelse",
    "investeringsfond", "PE-fond",

    # Regulatorisk & politikk
    "Legemiddelverket", "Folkehelseinstituttet", "FHI",
    "reseptfrihet", "markedsføringsloven", "markedsføring av",
    "Helse- og omsorgsdepartementet", "helsepolitikk",
    "helsestrategi", "folkehelse", "forebygging",
    "EU-regulering", "EFSA", "emballasje", "bærekraft",
    "plastforbudet", "grønn omstilling",

    # Økonomi & forbrukertrender
    "forbrukertrender", "forbrukervaner", "kjøpekraft",
    "prisvekst", "inflasjon", "kronekurs", "renteøkning",
    "handelsbalanse", "import", "eksport",
    "bærekraftig forbruk", "grønn forbruker",

    # Markedsføring & media
    "influencer", "sosiale medier", "digital markedsføring",
    "reklameforbudet", "merkevare", "brand",
    "TV-reklame", "reklamebransjen",

    # Helse generelt
    "legemiddel", "farmasi", "helsesektor", "bioteknologi",
    "helsekost", "naturmiddel", "kosttilskudd",
    "eldrebølge", "kronisk sykdom",
]

CLAUDE_MODEL  = "claude-haiku-4-5-20251001"
LOOKBACK_HOURS = 26


# ── RSS-henting ───────────────────────────────────────────────────────────────

def parse_published(entry):
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def keyword_match(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in KEYWORDS)


def fetch_recent_articles() -> list[dict]:
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    articles = []

    for source, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = parse_published(entry)
                    if pub and pub < cutoff:
                        continue
                    title   = getattr(entry, "title",   "").strip()
                    summary = getattr(entry, "summary", "").strip()
                    link    = getattr(entry, "link",    "").strip()
                    if not title or not link:
                        continue
                    if not keyword_match(title + " " + summary):
                        continue
                    articles.append({
                        "source":       source,
                        "title":        title,
                        "url":          link,
                        "ingress":      summary[:1000],
                        "published_at": pub.isoformat() if pub else None,
                    })
            except Exception as e:
                print(f"[WARN] Feil ved henting av {url}: {e}")

    seen, unique = set(), []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    print(f"[INFO] {len(unique)} unike artikler etter nøkkelord-filter")
    return unique


# ── Claude-klassifisering ─────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """Du er markedsintelligensanalytiker for Karo Healthcare Norge.
Karo eier Decubal, Locobase, Apobase (hudpleie/fuktighetskrem) og Flux (tannpleie/oral care).
Karo selger via apotek og dagligvare i Norge. Eid av PE-fondet KKR.

Vurder om nyheten er relevant for Karo – DIREKTE eller INDIREKTE.

Direkte relevante: hudpleie, eksem, tannpleie, apotek, OTC-legemidler, konkurrenter som Beiersdorf/Colgate, M&A i helsesektoren.

Indirekte relevante (inkluder disse også):
- Helsepolitikk og regulering som påvirker OTC-markedet
- Dagligvarebransjen: sortimentsendringer, prispress, kjedestrategi
- Forbrukertrender: prisvekst, kjøpekraft, bærekraft, merkevaretrender
- Markedsføring: nye regler, influencer-regler, digital reklame
- Norsk økonomi som påvirker forbrukermarkedet
- PE/M&A bredt i konsumentbransjen
- Helsepolitikk og folkehelse

Vær INKLUDERENDE – ved tvil, sett relevant=true med lav confidence.

Returner KUN gyldig JSON:
{
  "relevant": true,
  "category": "apotek",
  "confidence": 85,
  "summary": "1-2 setninger som forklarer hvorfor dette er relevant for Karo."
}

Kategorier: M&A | apotek | dagligvare | dermatologi | oral-care | konkurrenter | regulatorisk | forbrukertrender | helsepolitikk | markedsføring | økonomi | annet
confidence = 0-100."""


def classify_articles(articles: list[dict]) -> list[dict]:
    client   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    relevant = []

    for art in articles:
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=256,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": f"Tittel: {art['title']}\nIngress: {art['ingress']}\nKilde: {art['source']}"}],
            )
            raw = response.content[0].text.strip()

            # Fjern eventuelle markdown-backticks
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            print(f"[DEBUG] Svar for '{art['title'][:40]}': {raw[:100]}")

            result = json.loads(raw)
            if result.get("relevant") and result.get("confidence", 0) >= 60:
                art["category"]        = result.get("category", "annet")
                art["relevance_score"] = result.get("confidence", 0)
                art["summary"]         = result.get("summary", "")
                relevant.append(art)
        except Exception as e:
            print(f"[WARN] Klassifisering feilet for '{art['title']}': {e}")

    print(f"[INFO] {len(relevant)} artikler klassifisert som relevante")
    return relevant


# ── Supabase ──────────────────────────────────────────────────────────────────

def save_to_supabase(articles: list[dict]) -> list[dict]:
    sb  = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    new = []

    for art in articles:
        try:
            result = sb.table("articles").upsert(
                {
                    "title":           art["title"],
                    "url":             art["url"],
                    "source":          art["source"],
                    "published_at":    art.get("published_at"),
                    "ingress":         art.get("ingress", ""),
                    "summary":         art.get("summary", ""),
                    "category":        art.get("category", "annet"),
                    "relevance_score": art.get("relevance_score", 0),
                },
                on_conflict="url",
                ignore_duplicates=True,
            ).execute()
            if result.data:
                new.append(art)
        except Exception as e:
            print(f"[WARN] DB-feil for '{art['title']}': {e}")

    print(f"[INFO] {len(new)} nye artikler lagret i Supabase")
    return new


# ── Hovedflyt ─────────────────────────────────────────────────────────────────

def main():
    print(f"[START] {datetime.now().isoformat()}")

    articles = fetch_recent_articles()
    if not articles:
        print("[INFO] Ingen artikler passerte nøkkelord-filter. Avslutter.")
        return

    classified = classify_articles(articles)
    save_to_supabase(classified)

    print(f"[DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
