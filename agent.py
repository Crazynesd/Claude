import re
import requests
from bs4 import BeautifulSoup
import anthropic

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "get_youtube_transcript",
        "description": (
            "Hent transskript fra en YouTube-video. "
            "Returnerer den fulde tekst fra videoen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube-video URL, f.eks. https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                }
            },
            "required": ["url"],
        },
    }
]

SYSTEM = (
    "Du er en hjælpsom assistent, der kan hente og analysere transskripter fra YouTube-videoer. "
    "Når brugeren giver dig et YouTube-link, bruger du get_youtube_transcript-værktøjet til at hente transskriptet. "
    "Præsenter derefter transskriptet pænt og tilbyd at hjælpe med at opsummere, analysere eller besvare spørgsmål om indholdet."
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://youtubetotranscript.com/",
}


def extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    return match.group(1) if match else None


def fetch_transcript(url: str) -> str:
    video_id = extract_video_id(url)
    if not video_id:
        return f"Kunne ikke finde et gyldigt YouTube-video-ID i: {url}"

    transcript_url = f"https://youtubetotranscript.com/transcript?v={video_id}"

    try:
        response = requests.get(transcript_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Fejl ved hentning fra youtubetotranscript.com: {e}"

    soup = BeautifulSoup(response.text, "html.parser")

    # Siden viser transskriptet i <span>-tags med data-start attribut
    spans = soup.find_all("span", attrs={"data-start": True})
    if spans:
        text = " ".join(s.get_text(strip=True) for s in spans)
        return f"[Transskript hentet via youtubetotranscript.com]\n\n{text}"

    # Fallback: prøv div med id eller klasse der indeholder 'transcript'
    for selector in ["#transcript", ".transcript", "[class*='transcript']"]:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator=" ", strip=True)
            if len(text) > 100:
                return f"[Transskript hentet via youtubetotranscript.com]\n\n{text}"

    # Debug: returner sidens titel så vi ved hvad der skete
    title = soup.title.string if soup.title else "ukendt"
    return f"Kunne ikke finde transskript på siden. Side-titel: '{title}'"


def run_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_youtube_transcript":
        return fetch_transcript(tool_input["url"])
    return f"Ukendt værktøj: {tool_name}"


def chat():
    messages = []
    print("YouTube Transcript Agent")
    print("Skriv et YouTube-link for at hente transskriptet.")
    print("Skriv 'quit' for at afslutte.\n")

    while True:
        try:
            user_input = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nFarvel!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Farvel!")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        # Agentic loop
        while True:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        print(f"\nAssistent: {block.text}\n")
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"[Henter transskript fra: {block.input.get('url', '')}]")
                        result = run_tool(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
                continue

            break


if __name__ == "__main__":
    chat()
