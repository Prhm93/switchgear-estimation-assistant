# Recorded model runs

Saved LLM output for the app's **recorded** mode (Stage 3). Empty until Part B: the recordings are made by
`notebooks/04-colab-llm-extraction.ipynb` on a Colab T4 GPU from a zip of the files this laptop built
(`python -m backend.record pack`), never from files rebuilt elsewhere.

Layout: `<set>/<project>/<file>.json`, for example `test/T03/specification.pdf.json` or
`reworded/R08/drawing__schematic.dxf.json` ("/" in a file path becomes "__").

Each file is a `Recording` (`ai_engine/estimation_assistant/providers.py`): model name, model version
(Ollama digest), date, mode, prompt version, the full system prompt and prompt template, the SHA-256 of
the input file, and one entry per model call (SHA-256 of the prompt, the reply, seconds).

The app uses a recording only for a file with exactly that SHA-256, and replays a reply only for exactly
the same prompt; anything else is refused. Recordings made by the tests are labelled `"fake": true` and
are never stored here.
