# Claudepad — Stripsmith

Session memory. **Session Summaries** at the top (newest first, keep 20; move the
21st to `oldpad.md`). **Key Findings** at the bottom (permanent).

---

## Session Summaries

### 2026-06-17 11:24 UTC — Maintenance pass: fix broken LLM integration, deadlock, key wiring; add tests + docs

Repo had a working MVP but several latent breakages. Fixed:

1. **Retired/invalid Claude model IDs (critical).** `config/config.yaml` used
   `claude-3-opus-20240229` (retired 2026-01-05 → 404) and both code fallbacks
   used `claude-3-5-sonnet-20250514` (never valid). Every Stage 1/3 call would
   fail. Centralized the default as `DEFAULT_LLM_MODEL = "claude-opus-4-8"` in
   `src/utils/config.py`; config + both fallbacks now point there. Added
   `analysis.max_output_tokens` (8192) and made response parsing pull the first
   text block instead of assuming `content[0]`.
2. **Deadlock in `JobManager.cleanup_old_jobs`.** It held the non-reentrant
   `self._lock` and then called `self.delete_session()` (which re-acquires it) →
   permanent hang of the backend cleanup loop the moment any session expired.
   Now deletes expired sessions inline under the held lock.
3. **Wrong API key in `backend/api_wrapper.py`.** `PanelBreakdown()` was built
   with no `api_key`, so in the hosted (keyless) backend Stage 3 raised
   "ANTHROPIC_API_KEY not found". Now `PanelBreakdown(api_key=self.anthropic_key)`.
4. **Broken smart-quote normalization.** `_normalize_quotes` replacement keys had
   been flattened to ASCII (no-ops), so curly quotes from word processors were
   never normalized and dialogue detection missed quoted speech. Rewrote with
   real Unicode codepoints + explanatory comment.
5. **Python 3.12 modernization.** Replaced deprecated `datetime.utcnow()` (9 uses
   in `backend/jobs.py`) with a timezone-aware `_utcnow()` helper; removed an
   unused `datetime` import from `backend/main.py`.

Added `tests/` (pytest, 51 tests, fully offline) with regression guards for #1–#4
(notably a threaded timeout guard for the deadlock and a mocked end-to-end check
that the web pipeline threads user keys into every stage). Added `ARCHITECTURE.md`
and this `claudepad.md` (both required by user CLAUDE.md). Updated README
(Testing section, model credit), `.env.example`, and `config.yaml` comments.

Two-agent code review (correctness + test-quality) then ran: no correctness
issues; all four regression guards empirically confirmed to fail if their bug is
reintroduced. Two review-driven refinements applied: (a) `_normalize_quotes` keys
switched from literal curly chars to *named* Unicode escapes (`\N{...}`), so the
source itself is flatten-proof, not just the test; (b) `test_cleanup_then_lock_still_usable`
now runs cleanup in a timeout-guarded thread so a reintroduced deadlock fails
cleanly instead of hanging the whole pytest run.

Verification: `pytest` → 51 passed, 0 failures, no `datetime` deprecation
warnings. `reportlab` was pip-installed locally to let the export module import.

---

## Key Findings

- **Model config is single-sourced.** Change the Claude model in ONE place:
  `analysis.llm_model` in `config/config.yaml`. The in-code fallback is
  `DEFAULT_LLM_MODEL` in `src/utils/config.py`; keep them consistent.
  `tests/test_config.py` fails if a known-retired/invalid ID is ever configured.
- **`JobManager._lock` is non-reentrant.** Methods that take the lock
  (`delete_session`, `get_session`, etc.) must NOT be called from another method
  that already holds it — inline the work instead. This caused the cleanup
  deadlock.
- **Web backend uses the *user's* API keys, never the server's.** The hosted
  environment has no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`. Every pipeline
  component constructed in `backend/api_wrapper.py` must be passed the session's
  keys explicitly, or it will raise at construction time.
- **Quote literals in source are fragile.** Curly quotes written as literal
  characters can be silently flattened to ASCII on save. In `normalizer.py` they
  are intentional and load-bearing for dialogue detection — don't "tidy" them.
- **Dependencies:** `reportlab` is required by `src/compositor/export.py` (install
  it to run anything touching export/the web pipeline). `opencv-python` (`cv2`) is
  in `requirements.txt` but unused — reserved for Phase 2 speech bubbles.
- **Tests are offline.** No API keys or network needed; SDK clients can be
  constructed with dummy keys without making requests.
- **Web state is in-memory** (`JobManager`) ⇒ single backend process; a restart
  drops in-flight jobs. Scaling out needs an external store.
