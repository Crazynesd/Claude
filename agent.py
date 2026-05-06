import re
import sys
import anthropic
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

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


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_transcript(url: str) -> str:
    video_id = extract_video_id(url)
    if not video_id:
        return f"Kunne ikke finde et gyldigt YouTube-video-ID i: {url}"

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # Forsøg dansk, derefter engelsk, derefter hvad der er tilgængeligt
        try:
            transcript = transcript_list.find_transcript(["da", "en"])
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(
                [t.language_code for t in transcript_list]
            )

        entries = transcript.fetch()
        text = " ".join(entry.get("text", "") for entry in entries)
        language = transcript.language
        return f"[Transskript på {language}]\n\n{text}"

    except TranscriptsDisabled:
        return "Transskripter er deaktiveret for denne video."
    except NoTranscriptFound:
        return "Ingen transskripter fundet for denne video."
    except Exception as e:
        return f"Fejl ved hentning af transskript: {e}"


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
