"""Manual smoke test harness for the GAP1 pipeline."""

import argparse
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
_DEFAULT_AUDIO = _REPO_ROOT / "data" / "test_audio" / "meeting.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gap 1 pipeline on a WAV file.")
    parser.add_argument(
        "--audio",
        type=Path,
        default=_DEFAULT_AUDIO,
        help=f"Path to audio (default: {_DEFAULT_AUDIO})",
    )
    args = parser.parse_args()
    audio_path = args.audio.resolve()
    if not audio_path.is_file():
        print(
            f"Audio not found: {audio_path}\n"
            "Place a WAV at <repo-root>/data/test_audio/meeting.wav or pass --audio.",
            file=sys.stderr,
        )
        sys.exit(1)

    from pipeline.run_gap1 import run_gap1

    result = run_gap1(str(audio_path))

    print("\n--- TRANSCRIPT ---")
    for seg in result["transcript"][:3]:
        print(seg)

    print("\n--- SUMMARY ---")
    print(result["summary"])

    print("\n--- HIGHLIGHTS ---")
    for h in result["highlights"]:
        print(f"- {h['text']} (score={h['importance_score']:.2f})")

    print("\n--- SPEAKER CONTRIBUTION ---")
    for s in result["speakers"]:
        print(s)


if __name__ == "__main__":
    main()
