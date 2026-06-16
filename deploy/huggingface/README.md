---
title: PROSE-MEET
emoji: 🎙️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Prosody-aware meeting summarisation — upload audio, get transcript, importance & domain
---

# PROSE-MEET

Meeting audio pipeline: **faster-whisper** transcription, **Gap 1** utterance importance (prosody + semantics), **Gap 2** domain adaptation (SSL zero-shot).

**How to use:** Upload a short audio clip (30–90 s works best). First run after idle may take 1–2 minutes while the Space wakes up and loads models.

Source: [github.com/Gayaththri/PROSE-MEET](https://github.com/Gayaththri/PROSE-MEET)
