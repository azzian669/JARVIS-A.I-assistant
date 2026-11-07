# Legacy: JARVIS v1 (cloud prototype)

The first iteration of the project: speech-to-text via Google, the Gemini API as the language model with function calling, and edge-tts for speech output. It also holds an early `skills.py` experiment with OCR screen scanning and volume control.

It is kept for reference. The current version is in the repository root and runs its language model locally.

## Run

```bash
pip install -r requirements-legacy.txt
cp .env.example .env      # add your own GEMINI_API_KEY
python jarvis.py
```

Never commit `.env`.
