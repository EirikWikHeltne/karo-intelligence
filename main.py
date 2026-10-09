"""
Pharma News Agent – Karo Healthcare
Henter RSS-feeds daglig, filtrerer på Karo-relevans, klassifiserer med Claude API
(med en streng lokal reserveløsning), og lagrer relevante artikler i Supabase.
"""

import os
import re
import sys
import json
import html
import socket
import urllib.request
from urllib.parse import quote_plus, urlparse
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from supabase import create_client
except ImportError:
    create_client = None


# ── Konfigurasjon ─────────────────────────────────────────────────────────────

def google_news(query: str, lang: str = "no") -> str:
    """Google News-søk som RSS. `when:2d` holder resultatene ferske."""
    region = "NO:no" if lang == "no" else "NO:en"
    return (f"https://news.google.com/rss/search?q={quote_plus(query + ' when:2d')}"
            f"&hl={lang}&gl=NO&ceid={region}")


RSS_FEEDS = {
    # Norske kilder
    "VG":             ["https://www.vg.no/rss/feed/forsiden/",
                       "https://www.vg.no/rss/feed/?categories=1069"],
    "E24":            ["https://e24.no/rss2/",
                       "https://e24.no/rss2/?seksjon=boers-og-finans"],
    "NRK":            ["https://www.nrk.no/toppsaker.rss",
                       "https://www.nrk.no/norge/toppsaker.rss"],
    "Dagbladet":      ["https://www.dagbladet.no/?lab_viewport=rss"],
    "Aftenposten":    ["https://www.aftenposten.no/rss/"],
    "Dagsavisen":     ["https://www.dagsavisen.no/rss"],
    "DN":             ["https://services.dn.no/api/feed/rss/"],
    "Finansavisen":   ["https://ws.finansavisen.no/api/articles.rss",
                       "https://ws.finansavisen.no/api/articles.rss?category=B%C3%B8rs"],
    "Nettavisen":     ["https://www.nettavisen.no/service/rich-rss?tag=nyheter"],
    "TV2":            ["https://www.tv2.no/rss/nyheter/innenriks",
                       "https://www.tv2.no/rss/nyheter/utenriks"],
    "Dagens Medisin": ["https://www.dagensmedisin.no/rss"],
    "Farmatid":       ["https://www.farmatid.no/feed/"],
    "Dagligvarehandelen": ["https://www.dagligvarehandelen.no/feed/"],
    # Målrettede søk – treffer Karo, kunder og konkurrenter direkte, uansett avis
    "Google News":    [
        google_news('"Karo Healthcare" OR "Karo Pharma" OR Decubal OR Locobase OR Apobase'),
        google_news('Ibux OR Paracet OR "reseptfrie legemidler" OR egenomsorg'),
        google_news('"Apotek 1" OR Vitusapotek OR "Boots apotek" OR Farmasiet OR Apotera OR apotekbransjen'),
        google_news('eksem OR "tørr hud" OR hudpleie OR tannhelse OR tannkrem'),
        google_news('Haleon OR Kenvue OR Beiersdorf OR "consumer health" Nordic', lang="en"),
    ],
    # Internasjonale kilder (krever kjerne-treff, se STRICT_SOURCES)
    "NYT":            ["https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
                       "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"],
    "The Economist":  [google_news("site:economist.com health OR pharma OR consumer", lang="en")],
    "Fierce Pharma":  ["https://www.fiercepharma.com/rss/xml"],
    # Offentlige/bransje-kilder
    "FHI":            ["https://www.fhi.no/rss/nyheter/"],
    "SSB":            ["https://www.ssb.no/rss/"],
    "DMP":            ["https://www.dmp.no/rss/nyheter/"],        # Direktoratet for medisinske produkter
    "Helsedirektoratet": ["https://www.helsedirektoratet.no/rss"],
}

# Brede kilder der et enkelt kontekst-ord ikke er nok – artikkelen må treffe et kjerne-ord.
# (Fierce Pharma sendte tidligere alle 25 saker videre fordi "pharma" traff alt.)
STRICT_SOURCES = {"NYT", "The Economist", "Fierce Pharma", "SSB"}

FEED_TIMEOUT = 20
FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KaroIntelligence/1.0; +https://karo-intelligence.vercel.app)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.6",
    "Cookie": "CONSENT=YES+",  # unngå Googles samtykkeside
}

# ── Relevans-ordbok ───────────────────────────────────────────────────────────
# KJERNE: direkte relevant for Karos merker, kanaler, kategorier eller konkurrenter.
# KONTEKST: bakgrunn som bare teller sammen med andre treff.
# Ord matches fra ordstart (så "apotek" treffer "apotekene", men ikke "kapotek").
# Korte ord (≤4 tegn) må matche hele ordet. Regex-mønstre starter med "re:".
CORE_TERMS = {
    "karo": [
        "karo healthcare", "karo pharma", "decubal", "locobase", "apobase",
        "ibux", "paracet", "flux tann", "flux munn", "flux fluor",
    ],
    "dermatologi": [
        "hudpleie", r"re:eksem(?!pe)", "psoriasis", "atopisk", "tørr hud", "sensitiv hud",
        "barrierekrem", "fuktighetskrem", "hudkrem", "hudlege", "hudsykdom", "dermatolog",
        "skincare", "skin care", "eczema", "atopic dermatitis", "moisturiser", "moisturizer",
    ],
    "oral-care": [
        "tannpleie", "tannkrem", "munnskyll", "munnvann", "tannhelse", "karies",
        "munnhygiene", "fluortannkrem", "oral care", "oral health", "toothpaste", "mouthwash",
    ],
    "apotek": [
        "apotek", "vitusapotek", "boots apotek", "boots norge", "farmasiet", "apotera",
        "apotekforeningen", "legemiddelgrossist", "norsk medisinaldepot",
        "reseptfri", "reseptfritt", "reseptfrie", "otc", "egenomsorg", "selvmedisinering",
        "egenbehandling", "smertestillende", "ibuprofen", "paracetamol", "pillebruk",
        "pilleforbruk", "legemidler utenom apotek", "lua-ordningen",
        "over-the-counter", "self-care", "painkiller", "pain relief",
    ],
    "konkurrenter": [
        "beiersdorf", "eucerin", "nivea", "cerave", "la roche-posay", "vichy", "cetaphil",
        "bioderma", "haleon", "kenvue", "sensodyne", "colgate", "oral-b", "zendium",
        "solidox", "pepsodent", "panodil", "pinex", "paralgin", "voltaren", "nurofen",
        "orkla health", "perrigo", "stada",
    ],
    "M&A": ["consumer health", "konsumenthelse"],
    "regulatorisk": [
        "legemiddelverket", "direktoratet for medisinske produkter", "dmp",
        "legemiddelloven", "apotekloven", "reseptfrihet",
    ],
}
CONTEXT_TERMS = {
    "dagligvare": [
        "dagligvare", "rema 1000", "norgesgruppen", "coop", "kiwi", "meny", "spar",
        "hylleplass", "sortiment", "matkjede", "kjedemakt", "netthandel", "e-handel",
    ],
    "M&A": [
        "oppkjøp", "kjøper opp", "fusjon", "private equity", "oppkjøpsfond", "pe-fond",
        "kkr", "eqt", "nordic capital", "acquisition", "merger", "buyout", "takeover",
    ],
    "forbrukertrender": ["forbruker", "kjøpekraft", "matpris", "prisvekst", "handlevaner"],
    "økonomi": ["inflasjon", "kronekurs"],
    "markedsføring": ["influencer", "markedsføring", "reklame", "merkevare", "sosiale medier"],
    "helsepolitikk": [
        "folkehelse", "helsepolitikk", "legemiddel", "legemidler", "farmasi", "pharmacy",
        "pharma", "helsekost", "kosttilskudd", "allergi", "pollen", "solkrem", "sunscreen",
        "forkjølelse", "influensa", "unilever", "procter & gamble", "johnson & johnson",
        "l'oréal", "loreal",
    ],
}

# Ord som tyder på at et nøkkelord bare er kulisse (f.eks. "ran av apotek").
NOISE_TERMS = [
    "ran", "ranet", "pågrepet", "siktet", "tiltalt", "dømt", "drept", "drap", "knivstukket",
    "politiet", "brann", "ulykke", "omkom", "fotball", "kamp", "valgkamp",
]

BRAND_KEYWORDS = {
    "Decubal":  ["decubal"],
    "Locobase": ["locobase"],
    "Apobase":  ["apobase"],
    "Flux":     ["flux tannpleie", "flux tann", "flux munn", "flux fluor"],  # "flux" alene er for generisk
    "Ibux":     ["ibux"],
    "Paracet":  ["paracet"],
}

CLAUDE_MODEL   = "claude-haiku-4-5-20251001"
LOOKBACK_HOURS = 26
MIN_CLAUDE_SCORE = 65   # Claude-score som kreves for å lagre en sak
MIN_LOCAL_SCORE  = 60   # lokal score som kreves når API-et ikke er tilgjengelig


def _compile(term: str) -> re.Pattern:
    if term.startswith("re:"):
        body = term[3:]
    else:
        body = re.escape(term)
        if len(term) <= 4:
            body += r"(?!\w)"
    return re.compile(r"(?<!\w)" + body, re.IGNORECASE)


def _compile_terms(groups: dict) -> list[tuple[str, str, re.Pattern]]:
    return [(cat, t, _compile(t)) for cat, terms in groups.items() for t in terms]


CORE_PATTERNS    = _compile_terms(CORE_TERMS)
CONTEXT_PATTERNS = _compile_terms(CONTEXT_TERMS)
BRAND_PATTERNS   = {b: [_compile(k) for k in kws] for b, kws in BRAND_KEYWORDS.items()}
NOISE_PATTERNS   = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.IGNORECASE) for t in NOISE_TERMS]
KARO_CATEGORY    = {"Decubal": "dermatologi", "Locobase": "dermatologi", "Apobase": "dermatologi",
                    "Flux": "oral-care", "Ibux": "apotek", "Paracet": "apotek"}


def match_terms(text: str) -> tuple[list, list]:
    core = [(c, t) for c, t, p in CORE_PATTERNS if p.search(text)]
    ctx  = [(c, t) for c, t, p in CONTEXT_PATTERNS if p.search(text)]
    return core, ctx


def find_brands(text: str) -> list[str]:
    return [b for b, pats in BRAND_PATTERNS.items() if any(p.search(text) for p in pats)]


def passes_prefilter(source: str, text: str) -> bool:
    core, ctx = match_terms(text)
    if core:
        return True
    return source not in STRICT_SOURCES and len({t for _, t in ctx}) >= 2


def clean_text(raw: str) -> str:
    """Fjern HTML-tagger og entiteter fra RSS-ingress."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# ── RSS-henting ───────────────────────────────────────────────────────────────

_BAD_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BARE_AMP      = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)")


def fetch_feed(url: str):
    """Hent feed med timeout og nettleser-lik User-Agent, og rens vanlige XML-feil
    (kontrolltegn og nakne &) som ellers gir 'not well-formed (invalid token)'."""
    req = urllib.request.Request(url, headers=FEED_HEADERS)
    with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    feed = feedparser.parse(raw)
    if getattr(feed, "bozo", 0) and not feed.entries:
        text = raw.decode(charset, errors="replace")
        text = _BARE_AMP.sub("&amp;", _BAD_XML_CHARS.sub("", text))
        feed = feedparser.parse(text)
    return feed


def parse_published(entry):
    # feedparser forsøker selv å parse dato til struct_time – bruk det først,
    # så faller vi tilbake til rå strenger (RFC 2822) for feeds som ikke gir oss det.
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def _entry_source(source: str, entry) -> tuple[str, str]:
    """For Google News: bruk faktisk utgiver som kilde og fjern ' - Utgiver' fra tittelen."""
    title = clean_text(getattr(entry, "title", ""))
    if source == "Google News" or "news.google.com" in getattr(entry, "link", ""):
        publisher = (getattr(entry, "source", None) or {}).get("title", "")
        if publisher:
            if title.endswith(" - " + publisher):
                title = title[: -len(publisher) - 3].strip()
            return publisher, title
    return source, title


def _title_key(title: str) -> str:
    return re.sub(r"[^\w]+", "", title.lower())[:80]


def fetch_recent_articles() -> list[dict]:
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    articles = []
    broken   = []

    for source, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = fetch_feed(url)
            except Exception as e:
                broken.append(source)
                print(f"[WARN] Feil ved henting av {source} {url}: {type(e).__name__}: {e}")
                continue
            total = len(feed.entries)
            bozo_reason = ""
            if getattr(feed, "bozo", 0) and not total:
                bozo_reason = f" bozo={type(feed.bozo_exception).__name__}: {feed.bozo_exception}"
                broken.append(source)
            old = no_title = no_match = kept = 0
            for entry in feed.entries:
                pub = parse_published(entry)
                if pub and pub < cutoff:
                    old += 1
                    continue
                art_source, title = _entry_source(source, entry)
                summary = clean_text(getattr(entry, "summary", ""))
                link    = getattr(entry, "link", "").strip()
                if not title or not link:
                    no_title += 1
                    continue
                if not passes_prefilter(source, title + " " + summary):
                    no_match += 1
                    continue
                kept += 1
                articles.append({
                    "source":       art_source,
                    "title":        title,
                    "url":          link,
                    "ingress":      summary[:1000],
                    # Bruk nåtidspunkt som fallback hvis feeden mangler publiseringsdato
                    "published_at": (pub or datetime.now(timezone.utc)).isoformat(),
                })
            print(f"[FEED] {source} {url[:90]} → entries={total} old={old} no_title={no_title} no_match={no_match} kept={kept}{bozo_reason}")

    # Fjern duplikater – både samme URL og samme sak fra flere kilder (lik tittel)
    seen_urls, seen_titles, unique = set(), set(), []
    for a in articles:
        tk = _title_key(a["title"])
        if a["url"] in seen_urls or tk in seen_titles:
            continue
        seen_urls.add(a["url"]); seen_titles.add(tk)
        unique.append(a)

    if broken:
        print(f"::warning::{len(set(broken))} kilder ga ingen data denne kjøringen: {', '.join(sorted(set(broken)))}")
    print(f"[INFO] {len(unique)} unike artikler etter relevans-filter (før dedup: {len(articles)})")
    return unique


# ── Claude-klassifisering ─────────────────────────────────────────────────────

CLASSIFY_SYSTEM = """Du er markedsintelligensanalytiker for Karo Healthcare Norge. Du filtrerer nyheter
for markeds- og salgsteamet. Teamet vil KUN se saker de kan handle på – heller få gode saker enn mange svake.

OM KARO I NORGE (eid av PE-fondet KKR):
• Decubal og Locobase – fuktighets-/barrierekremer mot tørr hud og eksem. Selges KUN via apotek.
• Apobase – hudpleie, apotek.
• Flux – fluorskyll/tannpleie. Apotek og dagligvare.
• Ibux (ibuprofen) og Paracet (paracetamol) – reseptfrie smertestillende. Apotek og dagligvare (LUA).
Kunder/kanaler: apotekkjedene (Apotek 1, Vitusapotek, Boots, Farmasiet, Apotera, Ditt Apotek),
grossister (NMD, Alliance), dagligvare (NorgesGruppen, Rema 1000, Coop).
Konkurrenter: Beiersdorf (Eucerin, Nivea), L'Oréal (CeraVe, La Roche-Posay), Haleon (Sensodyne, Voltaren,
Panodil), Kenvue, Colgate, Orkla Health, Perrigo, apotekkjedenes egne merker.

SCORE (0–100) – hvor nyttig er saken for Karos markeds- og salgsteam i Norge/Norden?
90–100: Nevner et Karo-merke, Karo selv, eller en vesentlig hendelse hos en konkurrent eller kunde
        (lansering, oppkjøp, tilbakekalling, kjedeendring, prisendring).
75–89:  Direkte i Karos kategorier i Norge/Norden: hudpleie/eksem, tannhelse, reseptfrie smertestillende,
        apotekmarkedet, regelverk for reseptfrie legemidler/apotek/markedsføring av legemidler.
60–74:  Klar indirekte effekt: dagligvarekjedenes helse/skjønnhet-sortiment, M&A i consumer health,
        forbrukertrender innen helse og egenomsorg, folkehelsedata om hud, tenner eller smertestillende.
0–59:   Alt annet. Eksempler: generell makroøkonomi, renter, generell prisvekst, kriminalitet, sport,
        politikk uten kobling til helse/handel, reseptbelagte legemidler, biotek-studier, amerikansk
        legemiddelpris/forsikring, saker der et nøkkelord bare er nevnt i forbifarten.

"relevant" = true kun hvis score >= 65. Vær streng: ved tvil, sett lavere score.
"brands": Karo-merker som faktisk er nevnt i teksten (Decubal, Locobase, Apobase, Flux, Ibux, Paracet), ellers [].
"summary": 1–2 setninger på norsk: hva skjedde, og konkret hva det betyr for Karo (hvilket merke, kanal eller
konkurrent). Ikke gjenta tittelen. Ikke skriv generelle fraser som "kan være relevant for Karo".

Kategorier: M&A | apotek | dagligvare | dermatologi | oral-care | konkurrenter | regulatorisk |
forbrukertrender | helsepolitikk | markedsføring | økonomi | annet

Svar KUN med gyldig JSON, uten markdown:
{"relevant": true, "score": 82, "category": "apotek", "brands": [], "summary": "..."}"""

VALID_CATEGORIES = {"M&A", "apotek", "dagligvare", "dermatologi", "oral-care", "konkurrenter",
                    "regulatorisk", "forbrukertrender", "helsepolitikk", "markedsføring", "økonomi", "annet"}


def _local_category(core, ctx, brands) -> str:
    if brands:
        return KARO_CATEGORY[brands[0]]
    weights = {}
    for cat, _ in core:
        if cat == "karo":
            continue
        weights[cat] = weights.get(cat, 0) + 3
    for cat, _ in ctx:
        weights[cat] = weights.get(cat, 0) + 1
    return max(weights, key=weights.get) if weights else "annet"


def local_score(title: str, ingress: str) -> tuple[int, str, list[str]]:
    """Regelbasert Karo-score. Uten kjerne-treff blir maks 45 – dvs. aldri lagret."""
    text = f"{title} {ingress}"
    core, ctx = match_terms(text)
    core_terms = {t for _, t in core}
    ctx_terms  = {t for _, t in ctx}
    brands = find_brands(text)
    if core_terms:
        score = 40 + 15 * min(len(core_terms), 3) + 5 * min(len(ctx_terms), 3)
        title_core, _ = match_terms(title)
        if title_core:
            score += 10
    else:
        score = 25 + 5 * min(len(ctx_terms), 4)
    if brands or any(c == "karo" for c, _ in core):
        score += 30
    elif any(p.search(text) for p in NOISE_PATTERNS):
        score -= 25
    return max(0, min(score, 95)), _local_category(core, ctx, brands), brands


def classify_articles_local(articles: list[dict]) -> list[dict]:
    """Lokal klassifisering – brukes når Claude API ikke er tilgjengelig."""
    relevant = []
    for art in articles:
        score, cat, brands = local_score(art["title"], art.get("ingress", ""))
        if score < MIN_LOCAL_SCORE:
            continue
        ingress = art.get("ingress", "")
        art["category"]        = cat
        art["relevance_score"] = score
        # Vis artikkelens egen ingress i appen i stedet for en teknisk merknad
        art["summary"]         = (ingress[:240].rsplit(" ", 1)[0] + "…") if len(ingress) > 240 else ingress
        art["brand"]           = ",".join(brands) if brands else None
        relevant.append(art)

    print(f"[INFO] {len(relevant)} av {len(articles)} artikler holdt lokal relevans-terskel ({MIN_LOCAL_SCORE})")
    return relevant


class APIUnavailableError(Exception):
    """Raised when the Claude API is unusable (auth, billing, etc.).
    Bærer med seg det som allerede er klassifisert, og det som gjenstår."""
    def __init__(self, msg, relevant=None, remaining=None):
        super().__init__(msg)
        self.relevant  = relevant or []
        self.remaining = remaining or []


def _parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"Ingen JSON i svar: {text[:120]}")
    return json.loads(text[start:end])


def classify_articles(articles: list[dict]) -> list[dict]:
    """Klassifiserer artikler med Claude API."""
    client   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"].strip())
    relevant = []
    consecutive_failures = 0
    streak_start = 0

    for i, art in enumerate(articles):
        if consecutive_failures == 0:
            streak_start = i
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=400,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": f"Kilde: {art['source']}\nTittel: {art['title']}\nIngress: {art['ingress']}"}],
            )
            consecutive_failures = 0
            raw = next((b.text for b in response.content if b.type == "text"), "")
            result = _parse_json(raw)
            score = int(result.get("score", result.get("confidence", 0)) or 0)
            print(f"[CLAUDE] {score:3d} {'✓' if score >= MIN_CLAUDE_SCORE else '·'} {art['source']}: {art['title'][:70]}")
            if result.get("relevant") and score >= MIN_CLAUDE_SCORE:
                cat = result.get("category", "annet")
                art["category"]        = cat if cat in VALID_CATEGORIES else "annet"
                art["relevance_score"] = score
                art["summary"]         = result.get("summary", "")
                # Stol bare på merker som faktisk står i teksten
                text_brands = set(find_brands(f"{art['title']} {art['ingress']}"))
                brands = [b for b in result.get("brands", []) if b in BRAND_KEYWORDS] or sorted(text_brands)
                art["brand"] = ",".join(brands) if brands else None
                relevant.append(art)
        except anthropic.AuthenticationError as e:
            raise APIUnavailableError(f"Ugyldig API-nøkkel: {e}", relevant, articles[i:])
        except anthropic.BadRequestError as e:
            # F.eks. "credit balance is too low" – gjelder alle kall, ingen vits å fortsette
            if "credit balance" in str(e).lower():
                raise APIUnavailableError("Anthropic-kontoen er tom for kreditt – fyll på under Plans & Billing",
                                          relevant, articles[i:])
            print(f"[WARN] Klassifisering feilet for '{art['title'][:60]}': {e}")
            consecutive_failures += 1
        except Exception as e:
            print(f"[WARN] Klassifisering feilet for '{art['title'][:60]}': {e}")
            consecutive_failures += 1
        if consecutive_failures >= 3:
            raise APIUnavailableError(f"API utilgjengelig etter {consecutive_failures} feil på rad",
                                      relevant, articles[streak_start:])

    print(f"[INFO] {len(relevant)} av {len(articles)} artikler vurdert som relevante av Claude (terskel {MIN_CLAUDE_SCORE})")
    return relevant


# ── Lagring ──────────────────────────────────────────────────────────────────

def supabase_env() -> tuple[str, str]:
    """Les og rens Supabase-hemmeligheter (mellomrom/linjeskift i secrets gir DNS-feil)."""
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if url and not url.startswith("http"):
        url = "https://" + url
    return url, key


def check_supabase_host(url: str) -> bool:
    """Sjekk at Supabase-verten finnes før vi bruker tid på klassifisering."""
    host = urlparse(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        print("::error::SUPABASE_URL peker til en vert som ikke finnes (DNS-oppslag feilet). "
              "Sjekk GitHub-secreten SUPABASE_URL – den skal være https://<prosjekt-id>.supabase.co, "
              "samme prosjekt som i index.html. Prosjektet kan også være slettet/pauset i Supabase.")
        return False


def known_urls(sb) -> set[str]:
    """URL-er som allerede er lagret de siste dagene – disse trenger ikke klassifiseres på nytt."""
    since = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    try:
        res = sb.table("articles").select("url").gte("created_at", since).limit(5000).execute()
        return {r["url"] for r in (res.data or [])}
    except Exception as e:
        print(f"[WARN] Kunne ikke hente eksisterende URL-er: {e}")
        return set()


def save_to_supabase(sb, articles: list[dict]) -> bool:
    if not articles:
        print("[INFO] Ingen artikler å lagre – hopper over Supabase-upsert.")
        return True

    payload = [
        {
            "title":           art["title"],
            "url":             art["url"],
            "source":          art["source"],
            "published_at":    art.get("published_at"),
            "ingress":         art.get("ingress", ""),
            "summary":         art.get("summary", ""),
            "category":        art.get("category", "annet"),
            "relevance_score": art.get("relevance_score", 0),
            "brand":           art.get("brand"),
        }
        for art in articles
    ]

    try:
        result = sb.table("articles").upsert(
            payload,
            on_conflict="url",
            ignore_duplicates=True,
        ).execute()
        saved = result.data or []
        print(f"[INFO] Upsert ferdig. Returnerte {len(saved)} nye rader (forsøkte {len(payload)}).")
        if len(payload) and not saved:
            print("[INFO] Ingen nye rader – alle URL-er var allerede i databasen (ON CONFLICT DO NOTHING).")
        return True
    except Exception as e:
        import traceback
        print(f"::error::DB-feil under lagring til Supabase: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def save_to_json(articles: list[dict]) -> None:
    """Lagrer artikler til lokal JSON-fil når Supabase ikke er tilgjengelig."""
    outfile = f"articles_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%MZ')}.json"
    payload = [
        {
            "title":           art["title"],
            "url":             art["url"],
            "source":          art["source"],
            "published_at":    art.get("published_at"),
            "ingress":         art.get("ingress", ""),
            "summary":         art.get("summary", ""),
            "category":        art.get("category", "annet"),
            "relevance_score": art.get("relevance_score", 0),
            "brand":           art.get("brand"),
        }
        for art in articles
    ]
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[INFO] {len(payload)} artikler lagret til {outfile}")


# ── Hovedflyt ─────────────────────────────────────────────────────────────────

def main():
    print(f"[START] {datetime.now().isoformat()}")

    sb_url, sb_key = supabase_env()
    has_api = bool(anthropic and os.environ.get("ANTHROPIC_API_KEY", "").strip())
    has_db  = bool(create_client and sb_url and sb_key)

    if not has_api:
        print("::warning::ANTHROPIC_API_KEY ikke satt – bruker lokal (regelbasert) klassifisering")
    if not has_db:
        print("[INFO] Supabase ikke konfigurert – lagrer til lokal JSON-fil")

    sb = None
    if has_db:
        if not check_supabase_host(sb_url):
            sys.exit(1)
        sb = create_client(sb_url, sb_key)

    articles = fetch_recent_articles()
    if sb is not None:
        seen = known_urls(sb)
        before = len(articles)
        articles = [a for a in articles if a["url"] not in seen]
        print(f"[INFO] {before - len(articles)} allerede lagret – {len(articles)} nye å vurdere")
    if not articles:
        print("[INFO] Ingen nye artikler passerte relevans-filteret. Avslutter.")
        return

    if has_api:
        try:
            classified = classify_articles(articles)
        except APIUnavailableError as e:
            print(f"::warning::Claude API utilgjengelig: {e}. Bruker streng lokal klassifisering for {len(e.remaining)} saker.")
            classified = e.relevant + classify_articles_local(e.remaining)
    else:
        classified = classify_articles_local(articles)

    if sb is not None:
        if not save_to_supabase(sb, classified):
            sys.exit(1)
    else:
        save_to_json(classified)

    print(f"[DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
