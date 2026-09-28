"""Price a booking request from the UI on the command line (the static-page route; with
src/ui/serve.py running, the page does this itself).

    python3 src/ui/price_request.py request.json -o mine.json

Then load mine.json in the page under "Developer: load another SuggestionSet".
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ui.engine import price_request  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("request")
    ap.add_argument("-o", "--out", default="suggestion_set.json")
    args = ap.parse_args()
    sset, errors = price_request(json.loads(Path(args.request).read_text()))
    Path(args.out).write_text(json.dumps(sset, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}: {len(sset['suggestions'])} suggestion(s), estimate {sset['estimate']['kg']['typ']} kg CO2e")
    print("contract: OK" if not errors else "contract: INVALID\n - " + "\n - ".join(errors))


if __name__ == "__main__":
    main()
