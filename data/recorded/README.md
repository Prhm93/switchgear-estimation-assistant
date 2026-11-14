# Recorded model runs

Saved LLM output for the app's **recorded** mode (Stage 3). The recordings are made by
`notebooks/04-colab-llm-extraction.ipynb` on a Colab T4 GPU from a zip of the files this laptop built
(`python -m backend.record pack`), never from files rebuilt elsewhere. They are not committed. The steps
for all three recordings (language model, drawing reading, question box) are in `docs/recording-model-answers.md`.

Layout: `<set>/<project>/<file>.json`, for example `test/T03/specification.pdf.json` or
`reworded/R08/drawing__schematic.dxf.json` ("/" in a file path becomes "__").

Each file is a `Recording` (`ai_engine/estimation_assistant/providers.py`): model name, model version
(Ollama digest), date, mode, prompt version, the full system prompt and prompt template, the SHA-256 of
the input file, and one entry per model call (SHA-256 of the prompt, the reply, seconds). Schema 1.1
(Stage 3b) also keeps, per call, Ollama's `done_reason` ("stop" when the reply finished, "length" when a
limit cut it off) and token counts, and the model options of the run (`num_ctx`, `num_predict`).

This folder holds the recordings of the **current** prompt (`backend/app/llm/prompt.py`,
`PROMPT_VERSION`). The Stage 3 Part A recordings (prompt `llm-extract-1`, schema 1.0) live in
`data/recorded-v1/` with the same layout; `python -m backend.evaluate` scores both side by side. The app
cannot replay them any more (their system prompt differs from the current one, so replay is refused and
the app reads with the rules).

The app uses a recording only for a file with exactly that SHA-256, and replays a reply only for exactly
the same prompt; anything else is refused. Recordings made by the tests are labelled `"fake": true` and
are never stored here.
