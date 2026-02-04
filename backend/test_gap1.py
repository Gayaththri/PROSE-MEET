from pipeline.run_gap1 import run_gap1

if __name__ == "__main__":
    audio_path = "../data/test_audio/meeting.wav"  

    result = run_gap1(audio_path)

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
