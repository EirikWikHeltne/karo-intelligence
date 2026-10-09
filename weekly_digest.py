"""
Weekly Digest – Karo Healthcare
Kjører hver fredag, henter ukens artikler fra Supabase og lager en kort
nøkkelord-basert oppsummering (ingen AI/API-kostnad) i weekly_summaries-tabellen.
"""

import os
from collections import Counter
from supabase import create_client
from datetime import datetime, timezone, timedelta

MIN_SCORE = 60  # samme terskel som appen bruker for "sterke treff"

CAT_LABELS = {
    "M&A": "M&A", "apotek": "apotek/reseptfritt", "dagligvare": "dagligvare",
    "dermatologi": "hudpleie", "oral-care": "tannhelse", "konkurrenter": "konkurrenter",
    "regulatorisk": "regulatorisk", "forbrukertrender": "forbrukertrender",
    "helsepolitikk": "helsepolitikk", "markedsføring": "markedsføring", "økonomi": "økonomi",
    "annet": "annet",
}


def fetch_week_articles(sb) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    result = sb.table("articles").select("title,source,category,brand,relevance_score") \
        .gte("published_at", since) \
        .gte("relevance_score", MIN_SCORE) \
        .order("relevance_score", desc=True) \
        .limit(200) \
        .execute()
    return result.data or []


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " og " + items[-1]


def build_digest(articles: list[dict]) -> dict:
    cats = Counter(a.get("category") or "annet" for a in articles)
    top_cats = [CAT_LABELS.get(c, c) for c, _ in cats.most_common(2)]
    brands = Counter(b.strip() for a in articles for b in (a.get("brand") or "").split(",") if b.strip())

    title = f"Mest om {_join(top_cats)}"
    parts = [f"{len(articles)} relevante saker denne uken."]
    top = articles[:3]
    if top:
        parts.append("Viktigst: " + _join([f"«{a['title']}» ({a.get('source', '')})" for a in top]) + ".")
    if brands:
        parts.append("Karo-merker nevnt: " + _join([f"{b} ({n})" for b, n in brands.most_common()]) + ".")
    spread = [f"{CAT_LABELS.get(c, c)} {n}" for c, n in cats.most_common(5)]
    parts.append("Fordeling: " + ", ".join(spread) + ".")
    return {"title": title, "summary": " ".join(parts)}


def save_digest(sb, digest: dict, article_count: int):
    now = datetime.now(timezone.utc)
    # Bruk ukens mandag som week_start – stabilt uavhengig av hvilken dag digesten kjøres.
    monday = (now - timedelta(days=now.weekday())).date()
    sb.table("weekly_summaries").insert({
        "title":         digest["title"],
        "summary":       digest["summary"],
        "article_count": article_count,
        "week_start":    monday.isoformat(),
        "created_at":    now.isoformat(),
    }).execute()
    print(f"[OK] Ukesdigest lagret: {digest['title']}")


def main():
    print(f"[START] Weekly digest {datetime.now().isoformat()}")

    url = os.environ["SUPABASE_URL"].strip().rstrip("/")
    sb = create_client(url, os.environ["SUPABASE_KEY"].strip())

    articles = fetch_week_articles(sb)
    if len(articles) < 3:
        print(f"[INFO] Bare {len(articles)} relevante artikler denne uken – hopper over digest.")
        return

    digest = build_digest(articles)
    save_digest(sb, digest, len(articles))

    print(f"[DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
