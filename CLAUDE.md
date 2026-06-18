# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Streamlit web app scaffold (Korean UI) that will consume the OpenAI API. Managed with [uv](https://docs.astral.sh/uv/); Python 3.13 pinned via `.python-version`.

## Commands

Use `uv` for everything — it manages the venv and the lock file. Do not invoke `pip` directly.https://github.com/gongja-ko/streamlit-myproject.git

- Install / sync dependencies: `uv sync`
- Add a dependency: `uv add <package>` (updates `pyproject.toml` and `uv.lock`)
- Run the Streamlit app: `uv run streamlit run app.py`
- Run the CLI entry point: `uv run python main.py`
- Run an arbitrary script in the project env: `uv run python <script.py>`

There is no test suite, linter, or formatter configured yet.

## Layout

- `app.py` — the Streamlit entry point. This is the actual application; `streamlit run app.py` is what the user launches.
- `main.py` — uv's default scaffold entry point (`print("Hello ...")`). Not used by the Streamlit app; safe to repurpose or remove.
- `.env` — for secrets (e.g. `OPENAI_API_KEY`). Loaded via `python-dotenv`; not committed (the file exists but `.gitignore` should be extended if real secrets are added — currently only `.venv` and Python build artifacts are ignored, so `.env` is **not** gitignored yet).

## Notes for future changes

- The Streamlit UI strings are in Korean. Keep new user-facing strings consistent unless the user asks otherwise.
- `openai` is declared as a dependency but not yet imported anywhere — when wiring it up, load the key with `dotenv.load_dotenv()` and read `os.environ["OPENAI_API_KEY"]` rather than hardcoding.
