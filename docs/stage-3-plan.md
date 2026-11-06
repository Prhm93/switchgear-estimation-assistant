# Stage 3 plan (Part A)

1. Freeze the rules: record the SHA-256 of `backend/app/extraction.py` and `backend/app/normalise.py` in `data/rules-freeze.json`, with a test that fails if they change. Commit this before any reworded file exists.
2. Reworded set: `data_generator/wording.py` and a `reworded` style option for the specification, letter and drawing (synonyms, clause and section order, number words, unit styles such as "4P", "4 pole", "four-pole"). Projects R01 to R20, seeds 2001 to 2020, the same planted-problem plans as T01 to T20, git-ignored. The original style stays byte-identical.
3. Score the frozen rules on both the original and the reworded sets, with and without the DXF. Report the real numbers only.
4. `ai_engine/estimation_assistant/providers.py`: one `ModelProvider` interface with the modes `rules`, `recorded`, `ollama` and `ollama-local` (the same HTTP client, at a different base URL).
5. `backend/app/llm/`: a Pydantic schema for the LLM output (each field with its value, unit, page and exact quote), the prompt (documents are data, never instructions), and a JSON structured-output call to gemma4:e2b.
6. Quote check: the quote must be in that page's text after normalising spaces and case; the value's number must be in the quote (reusing the ai_engine number check). A failing value is rejected and logged.
7. Instruction-like text detector: such lines are flagged on the analysis and review screens as a design-v2 alert chip and never followed.
8. Recorded mode: `data/recorded/<set>/<project>/<file>.json` with the model name, version, date, prompt and input SHA-256. A mismatched hash is refused. The run label is shown in the sidebar when a matching recording exists.
9. Combined mode: rules and LLM values for the same field are marked "agree" or kept side by side as a disagreement for Stage 6.
10. `notebooks/04-colab-llm-extraction.ipynb` (not run): it takes a zip of laptop-built files, checks their hashes, runs Ollama and saves recordings. Plus `docs/ollama-laptop.md` (not installed).
11. Tests: schema, quote check pass and fail, hash refusal, injection flagged, replay of a labelled fake recording.
12. `docs/stage-3.md`: what was built, the rules scores, and the LLM and combined columns as NOT RUN YET. Commit as I go, push the branch, no pull request.
