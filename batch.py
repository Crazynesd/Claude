import csv
import sys
from datetime import date
from pathlib import Path
import process

CSV_PATH = Path(__file__).parent / "urls.csv"


def load_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_rows(rows, fieldnames):
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = load_rows()
    if not rows:
        print("Ingen rækker i urls.csv")
        return
    fieldnames = list(rows[0].keys())
    pending = [r for r in rows if r.get("status") != "done"]
    print(f"{len(pending)} videoer at behandle (af {len(rows)} i alt)\n")
    for i, row in enumerate(rows, 1):
        if row.get("status") == "done":
            continue
        speaker = row["speaker"].strip()
        url = row["url"].strip()
        print(f"=== [{i}/{len(rows)}] {speaker} — {url} ===")
        try:
            saved = process.process(speaker, url)
            row["status"] = "done" if saved else "no-output"
            row["processed_date"] = date.today().isoformat()
            row["output_files"] = "; ".join(saved)
        except Exception as e:
            print(f"  FEJL: {e}")
            row["status"] = f"error: {str(e)[:80]}"
        save_rows(rows, fieldnames)
        print()
    done = sum(1 for r in rows if r.get("status") == "done")
    errors = sum(1 for r in rows if r.get("status", "").startswith("error"))
    print(f"Færdig: {done} succes, {errors} fejl, {len(rows)-done-errors} udestående")


if __name__ == "__main__":
    main()
