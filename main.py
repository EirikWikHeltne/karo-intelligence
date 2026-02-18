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
    # Karo-merker
    "Decubal", "Locobase", "Apobase", "Flux",
    # Hudpleie / dermatologi
    "hudpleie", "eksem", "psoriasis", "atopisk", "tørr hud", "barrierekrem",
    "fuktighetsgivende", "dermatologi", "hudsykdom", "sårpleie", "kløe",
    # Oral care
    "tannpleie", "munnhygiene", "fluor", "tannkrem", "munnvann", "tannskyll",
    "oral care", "tannhelse", "karies",
    # Apotek & dagligvare
    "apotek", "Apotek 1", "Vitusapotek", "Boots apotek",
    "Rema 1000", "NorgesGruppen", "Coop", "Kiwi", "Meny", "dagligvare",
    "hylleplass", "sortiment", "OTC", "reseptfri",
    # Konkurrenter
    "Beiersdorf", "Eucerin", "Nivea", "Unilever", "Vaseline",
    "La Roche-Posay", "Colgate", "Oral-B", "Sensodyne", "CeraVe", "Dove",
    # M&A & PE
    "oppkjøp", "fusjon", "kjøper", "selger", "transaksjon", "milliard",
    "private equity", "KKR", "Nordic Capital", "EQT", "Axel Johnson",
    "consumer health", "konsumenthelse",
    # Regulatorisk
    "Legemiddelverket", "Folkehelseinstituttet", "FHI", "Apotekforeningen",
    "markedsføring av legemidler", "reseptfrihet", "OTC-regelverket",
    # Generell helse/farmasi
    "legemiddel", "farmasi", "helsesektor", "bioteknologi",
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
Karo eier Decubal, Locobase, Apobase (hudpleie) og Flux (oral care), selger via apotek og dagligvare. Eid av KKR.

Returner KUN gyldig JSON – ingen markdown, ingen forklaringer:
{
  "relevant": true,
  "category": "apotek",
  "confidence": 85,
  "summary": "Norsk oppsummering på 1-2 setninger."
}

Kategorier: M&A | apotek | dagligvare | dermatologi | oral-care | konkurrenter | regulatorisk | legemiddel | helsesektor | annet
relevant = true kun hvis artikkelen er nyttig for Karo Healthcare.
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
            result = json.loads(response.content[0].text.strip())
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
