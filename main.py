"""
Pharma News Agent
Henter RSS-feeds daglig, klassifiserer med Claude API,
lagrer i Supabase og sender nyhetsbrev via Resend.
"""

import os
import json
import feedparser
import anthropic
import resend
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

# Nøkkelord for pre-filtrering – tilpasset Karo Healthcare
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
    "La Roche-Posay", "Colgate", "Oral-B", "Sensodyne",
    "Aquaphor", "CeraVe", "Dove",

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

CLAUDE_MODEL = "claude-sonnet-4-6"
LOOKBACK_HOURS = 26  # litt mer enn 24t for å ikke miste saker ved timing-avvik
NEWSLETTER_RECIPIENT = os.environ.get("NEWSLETTER_EMAIL", "eirik@example.com")
NEWSLETTER_SENDER = os.environ.get("NEWSLETTER_SENDER", "nyheter@yourdomain.com")


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────────

def parse_published(entry) -> datetime | None:
    """Henter publiseringstidspunkt fra RSS-entry."""
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def keyword_match(text: str) -> bool:
    """Sjekker om tekst inneholder relevante nøkkelord (case-insensitiv)."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in KEYWORDS)


def fetch_recent_articles(lookback_hours: int = LOOKBACK_HOURS) -> list[dict]:
    """Henter alle RSS-feeds og returnerer artikler nyere enn lookback_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    articles = []

    for source, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    pub = parse_published(entry)
                    # Hopp over artikler uten dato eller eldre enn cutoff
                    if pub and pub < cutoff:
                        continue

                    title   = getattr(entry, "title", "").strip()
                    summary = getattr(entry, "summary", "").strip()
                    link    = getattr(entry, "link", "").strip()

                    if not title or not link:
                        continue

                    # Pre-filtrering med nøkkelord
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

    # Dedupliser på URL
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    print(f"[INFO] {len(unique)} unike artikler etter nøkkelord-filter")
    return unique


# ── Claude-klassifisering ─────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """Du er en markedsintelligensanalytiker for Karo Healthcare Norge – et selskap som eier 
merkene Decubal, Locobase, Apobase (hudpleie) og Flux (oral care), og som selger via apotek og dagligvare.
Karo Healthcare er eid av KKR.

Vurder om nyhetsartikkelen er relevant for Karo Healthcare, og klassifiser den.

Returner KUN gyldig JSON uten markdown eller forklaringer:
{
  "relevant": true,
  "category": "M&A",
  "confidence": 85,
  "summary": "Kort norsk oppsummering på 1-2 setninger."
}

Gyldige kategorier:
- "M&A"          – oppkjøp, fusjoner, PE-transaksjoner i helse/consumer health
- "apotek"        – apotekkjedene, sortiment, hylleplass, forhandlinger
- "dagligvare"    – dagligvarekjeder, sortiment, OTC i grocery
- "dermatologi"   – hudpleie, eksem, hudsykdommer, barrierekremer
- "oral-care"     – tannpleie, munnhygiene, fluorprodukter
- "konkurrenter"  – Beiersdorf, Unilever, Colgate og andre konkurrenter
- "regulatorisk"  – Legemiddelverket, OTC-regler, markedsføringskrav
- "legemiddel"    – legemiddelmarkedet generelt
- "helsesektor"   – helsepolitikk, sykehus, bransjenyheter
- "annet"         – relevant men passer ikke over

relevant = true kun hvis artikkelen er tydelig nyttig for Karo Healthcare.
confidence = 0–100."""


def classify_articles(articles: list[dict]) -> list[dict]:
    """Klassifiserer artikler via Claude API. Returnerer kun relevante."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    relevant = []

    for art in articles:
        prompt = f"""Tittel: {art['title']}
Ingress: {art['ingress']}
Kilde: {art['source']}"""

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=256,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            result = json.loads(raw)

            if result.get("relevant") and result.get("confidence", 0) >= 60:
                art["category"]         = result.get("category", "annet")
                art["relevance_score"]  = result.get("confidence", 0)
                art["summary"]          = result.get("summary", "")
                relevant.append(art)
        except Exception as e:
            print(f"[WARN] Klassifisering feilet for '{art['title']}': {e}")

    print(f"[INFO] {len(relevant)} artikler klassifisert som relevante")
    return relevant


# ── Supabase ──────────────────────────────────────────────────────────────────

def save_to_supabase(articles: list[dict]) -> list[dict]:
    """Lagrer nye artikler i Supabase. Returnerer kun faktisk nye (ikke duplikater)."""
    supabase: Client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    new_articles = []
    for art in articles:
        try:
            result = supabase.table("articles").upsert(
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
                on_conflict="url",          # ignorer duplikater
                ignore_duplicates=True,     # ikke overskriv eksisterende
            ).execute()

            if result.data:                 # tom liste = duplikat
                new_articles.append(art)
        except Exception as e:
            print(f"[WARN] DB-feil for '{art['title']}': {e}")

    print(f"[INFO] {len(new_articles)} nye artikler lagret i Supabase")
    return new_articles


# ── Nyhetsbrev ────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "M&A":          "🤝",
    "legemiddel":   "💊",
    "helsesektor":  "🏥",
    "biotek":       "🔬",
    "apotek":       "⚕️",
    "annet":        "📰",
}

CATEGORY_ORDER = ["M&A", "biotek", "legemiddel", "apotek", "helsesektor", "annet"]


def build_newsletter_html(articles: list[dict], date_str: str) -> str:
    """Bygger HTML-nyhetsbrev gruppert etter kategori."""
    if not articles:
        return f"""<html><body style="font-family:sans-serif;max-width:680px;margin:auto;padding:24px">
        <h2>Helse & Pharma Nyheter – {date_str}</h2>
        <p>Ingen relevante saker funnet i dag.</p></body></html>"""

    # Grupper etter kategori
    grouped: dict[str, list] = {}
    for art in articles:
        cat = art.get("category", "annet")
        grouped.setdefault(cat, []).append(art)

    sections = ""
    for cat in CATEGORY_ORDER:
        if cat not in grouped:
            continue
        emoji = CATEGORY_EMOJI.get(cat, "📰")
        items = ""
        for art in sorted(grouped[cat], key=lambda x: x.get("relevance_score", 0), reverse=True):
            pub = art.get("published_at", "")[:10] if art.get("published_at") else ""
            items += f"""
            <div style="border-left:3px solid #0052cc;padding:12px 16px;margin:12px 0;background:#f8f9fa;border-radius:0 6px 6px 0">
              <div style="font-size:12px;color:#666;margin-bottom:4px">{art['source']} · {pub} · Score: {art.get('relevance_score',0)}</div>
              <a href="{art['url']}" style="font-size:16px;font-weight:600;color:#0052cc;text-decoration:none">{art['title']}</a>
              <p style="margin:8px 0 0;font-size:14px;color:#333">{art.get('summary','')}</p>
            </div>"""

        sections += f"""
        <h2 style="margin-top:32px;padding-bottom:8px;border-bottom:2px solid #e0e0e0;color:#1a1a1a">
          {emoji} {cat.upper()}
        </h2>{items}"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:auto;padding:24px;color:#1a1a1a">
  <div style="background:#0052cc;color:white;padding:20px 24px;border-radius:8px;margin-bottom:24px">
    <div style="font-size:12px;opacity:0.8;margin-bottom:4px">DAGLIG NYHETSBREV</div>
    <h1 style="margin:0;font-size:24px">Helse & Pharma Nyheter</h1>
    <div style="margin-top:4px;opacity:0.9">{date_str} · {len(articles)} saker</div>
  </div>
  {sections}
  <div style="margin-top:40px;padding-top:16px;border-top:1px solid #e0e0e0;font-size:12px;color:#999">
    Generert automatisk av Pharma News Agent · Arkiv tilgjengelig i Supabase
  </div>
</body></html>"""


def send_newsletter(articles: list[dict]):
    """Sender nyhetsbrev via Resend."""
    resend.api_key = os.environ["RESEND_API_KEY"]
    date_str = datetime.now().strftime("%-d. %B %Y")
    html = build_newsletter_html(articles, date_str)

    resend.Emails.send({
        "from":    NEWSLETTER_SENDER,
        "to":      [NEWSLETTER_RECIPIENT],
        "subject": f"💊 Helse & Pharma Nyheter – {date_str} ({len(articles)} saker)",
        "html":    html,
    })
    print(f"[INFO] Nyhetsbrev sendt til {NEWSLETTER_RECIPIENT}")


# ── Hovedflyt ─────────────────────────────────────────────────────────────────

def main():
    print(f"[START] {datetime.now().isoformat()}")

    articles  = fetch_recent_articles()
    if not articles:
        print("[INFO] Ingen artikler passerte nøkkelord-filter. Avslutter.")
        send_newsletter([])
        return

    classified = classify_articles(articles)
    new        = save_to_supabase(classified)
    send_newsletter(new)

    print(f"[DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
