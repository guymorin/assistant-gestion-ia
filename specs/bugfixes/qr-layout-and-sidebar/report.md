# Bugfix Report: Q&R Layout (Input at Top, Descending Chronology) and Sidebar Title

**Date:** 2026-11-14
**Status:** Fixed

## Description of the Issue

In the generic Q&R view, the text input zone appeared below the conversation history, and messages were displayed in ascending chronological order, making recent answers hard to find. The sidebar "Pièces jointes" block showed a verbose/HTML-like title instead of a clean "Pièces jointes" label, and the reason for the "Base introuvable" warning was unclear.

**Reproduction steps:**
1. Open any module Q&R view (RH, Finances, Juridique, Marketing).
2. Ask several questions.
3. Observe input at the bottom and oldest messages first.
4. Observe the sidebar warning when the base is not ingested.

**Impact:** Usability of the Q&R chat for all modules.

## Investigation Summary

Inspected `shared/qr_view.py` (`render_qr`, `render_pieces_jointes`) and the portal layout in `shared/ui.py`. Confirmed that `chat_input` was called after history rendering and that messages were iterated in insertion order.

## Discovered Root Cause

The Q&R render order placed `chat_input` after the history loop, and the history loop iterated `messages` in ascending order. The sidebar warning lacked an explanatory comment.

## Resolution for the Issue

- Moved `chat_input` (with accepted file formats PDF/TXT/Markdown) to the top of `render_qr`.
- Process submission without inline duplicate display; messages are appended to session state.
- Render history with `reversed(messages)` so newest answers appear first.
- Added a caption documenting accepted file formats.
- Added an explanatory comment for the "base introuvable" warning; kept the clean "Pièces jointes" expander title.

## Regression Test

**Test file:** `tests/test_finances_view.py`
**Test name:** `test_finances_view_mentions_detect_button_and_expander` (existing) plus full suite.

**Run command:** `.venv/bin/python -m pytest -q`

## Affected Files

| File | Change |
|------|--------|
| `shared/qr_view.py` | Reordered input/history, descending chronology, formats caption, warning comment |

## Verification

**Automated:**
- [x] Full test suite passes (232 passed, 14 deselected)

**Manual verification:**
- Input zone now at top; newest answers displayed first.

## Prevention

- Keep chat input above history for long conversations.
- Document accepted upload formats near the input.

## Related

- Prior fixes: avatar display, embedding guardrails, TVA UI fixes.
