import re
import sys
from datetime import date
from pathlib import Path
import anthropic
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound

client = anthropic.Anthropic()

DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-isaac@mallismedia.dk"
    / "My Drive/Main Claude/ecom-agents"
)

SUBDOMAINS = {
    "creative-strategist": ["winning-ads-analysis", "hooks", "new-concept-briefs"],
    "copy-agent": ["ad-copy", "product-texts", "email", "landing-pages"],
    "performance-analyst": ["ad-accounts", "spend-leaks", "budget-shifts", "mmm-light"],
    "lifecycle-crm": ["flows", "segments", "sequences"],
    "seo-content": ["keyword-research", "on-page", "geo"],
    "reporting": ["daily", "weekly", "anomaly-detection"],
}

ANALYSIS_PROMPT = """Du får et transskript fra en YouTube-video om e-commerce/marketing.

Din opgave: Lav én eller flere knowledge-filer ud fra videoen — én per relevant agent/subdomæne.

Tilgængelige agenter og subdomæner:
- creative-strategist: winning-ads-analysis, hooks, new-concept-briefs
- copy-agent: ad-copy, product-texts, email, landing-pages
- performance-analyst: ad-accounts, spend-leaks, budget-shifts, mmm-light
- lifecycle-crm: flows, segments, sequences
- seo-content: keyword-research, on-page, geo
- reporting: daily, weekly, anomaly-detection

For hver relevant kombination, output i præcis dette format:

AGENT: <agent>
SUBDOMAIN: <subdomain>
FILENAME: <kebab-case-emne>.md
---
# <Emne for denne agent>

**Speaker:** {speaker}
**Kilde:** {url}
**Dato:** {date}

## Indhold
<Fyldigt referat — gengiv hvad speaker siger uden fortolkning>

## Nøglepunkter
<Konkrete ting speaker siger om dette emne — bullets>

## Direkte citater
<Vigtige sætninger direkte fra transskriptet>

## Tags
#tag1 #tag2

===END===

Lav en sektion per agent/subdomain. Bevar ALT relevant indhold — filtrer ikke væk. Brugeren vurderer selv.
"""


def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def fetch_transcript(video_id):
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    try:
        t = transcript_list.find_transcript(["da", "en"])
    except NoTranscriptFound:
        t = transcript_list.find_generated_transcript(
            [tr.language_code for tr in transcript_list]
        )
    entries = t.fetch()
    return " ".join(
        getattr(e, "text", e.get("text", "") if isinstance(e, dict) else "")
        for e in entries
    )


def analyze(transcript, speaker, url):
    today = date.today().isoformat()
    prompt = (
        ANALYSIS_PROMPT
        + f"\n\nSpeaker: {speaker}\nURL: {url}\nDato: {today}\n\nTranskript:\n{transcript}"
    )
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def parse_and_save(analysis, speaker_slug):
    saved = []
    today = date.today().isoformat()
    for section in analysis.split("===END==="):
        section = section.strip()
        if not section:
            continue
        agent = re.search(r"AGENT:\s*(\S+)", section)
        sub = re.search(r"SUBDOMAIN:\s*(\S+)", section)
        fn = re.search(r"FILENAME:\s*(\S+)", section)
        if not (agent and sub and fn):
            continue
        agent, sub, fn = agent.group(1), sub.group(1), fn.group(1)
        if agent not in SUBDOMAINS or sub not in SUBDOMAINS[agent]:
            print(f"  Springer over ugyldig agent/subdomain: {agent}/{sub}")
            continue
        body = section.split("---", 1)
        if len(body) < 2:
            continue
        content = body[1].strip()
        out_dir = DRIVE_BASE / agent / sub / "_knowledge"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{today}_{speaker_slug}_{fn}"
        out_path.write_text(content, encoding="utf-8")
        saved.append(str(out_path.relative_to(DRIVE_BASE)))
    return saved


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def process(speaker, url):
    vid = extract_video_id(url)
    if not vid:
        print(f"Ugyldigt URL: {url}")
        return []
    print(f"[1/3] Henter transskript fra {url}...")
    transcript = fetch_transcript(vid)
    print(f"[2/3] Analyserer med Claude ({len(transcript)} tegn)...")
    analysis = analyze(transcript, speaker, url)
    print(f"[3/3] Gemmer knowledge-filer...")
    saved = parse_and_save(analysis, slugify(speaker))
    for p in saved:
        print(f"  ✓ {p}")
    return saved


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Brug: python3 process.py <speaker> <url>")
        sys.exit(1)
    process(sys.argv[1], sys.argv[2])
