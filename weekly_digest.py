"""
Weekly Digest – Karo Healthcare
Kjører hver fredag, henter ukens artikler fra Supabase,
genererer en AI-oppsummering med Claude, og lagrer i weekly_summaries-tabellen.
"""

import os
import json
import anthropic
from supabase import create_client
from datetime import datetime, timezone, timedelta


def fetch_week_articles(sb) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    result = sb.table("articles").select("*") \
        .gte("published_at", since) \
        .order("relevance_score", desc=True) \
        .limit(60) \
        .execute()
    return result.data or []


def generate_digest(articles: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Bygg artikkel-liste for Claude
    art_list = "\n".join([
        f"- [{a['category'].upper()}] {a['title']} ({a['source']}, score: {a.get('relevance_score',0)})"
        for a in articles[:40]
    ])

    prompt = f"""Du er en strategisk markedsanalytiker for Karo Healthcare Norway – et pharma-selskap som selger Decubal, Locobase, Apobase og Flux gjennom apotek og dagligvare i Norge.

Her er denne ukens mest relevante nyheter (sortert etter relevans):

{art_list}

Skriv en kortfattet ukesoppsummering på norsk med:
1. En kort, engasjerende tittel (maks 10 ord)
2. En oppsummering på 120–180 ord som:
   - Peker på de 2–3 viktigste trendene eller hendelsene fra uken
   - Knytter dem til Karos situasjon (hudpleie, oral care, apotek, dagligvare)
   - Avslutter med ett konkret spørsmål eller utfordring Karo bør tenke på

Svar KUN med gyldig JSON i dette formatet (ingen markdown, ingen forklaring):
{{"title": "...", "summary": "..."}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()

    # Strip markdown code fences if Claude wraps response in ```json ... ```
    if "```" in text:
        text = text.split("```")[-2] if text.count("```") >= 2 else text
        text = text.lstrip("json").strip()

    # Extract JSON object if there's surrounding text
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Ingen JSON funnet i Claude-svar: {text[:200]}")
    text = text[start:end]

    return json.loads(text)


def save_digest(sb, digest: dict, article_count: int):
    sb.table("weekly_summaries").insert({
        "title":         digest["title"],
        "summary":       digest["summary"],
        "article_count": article_count,
        "week_start":    (datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat(),
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }).execute()
    print(f"[OK] Ukesdigest lagret: {digest['title']}")


def main():
    print(f"[START] Weekly digest {datetime.now().isoformat()}")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    articles = fetch_week_articles(sb)
    if len(articles) < 3:
        print(f"[INFO] Bare {len(articles)} artikler denne uken – hopper over digest.")
        return

    print(f"[INFO] {len(articles)} artikler funnet – genererer digest...")
    digest = generate_digest(articles)
    save_digest(sb, digest, len(articles))

    print(f"[DONE] {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
