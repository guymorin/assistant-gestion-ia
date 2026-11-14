# Bugfix Report: Embedding Upsert Error and Avatar Display Issues

## Bug 1: Embedding Upsert Error

### Bug Description

**Error**: "Expected Embeddings to be non-empty list or numpy array, got [] in upsert"
**Trigger**: Asking questions about RH topics (e.g., "durée légale du travail")
**Location**: Vue RH de l'assistant de gestion

### Root Cause

When documents with empty `page_content` were added to the ChromaDB vectorstore, the upsert operation failed because ChromaDB cannot generate embeddings for empty text. This occurred during vectorstore creation.

### Fix Applied

Modified `ingest.py::creer_vectorstore()` to filter out empty documents before creating the ChromaDB vectorstore:

```python
# Filtrer les chunks vides pour éviter l'erreur d'upsert avec des embeddings vides
chunks_non_vides = [c for c in chunks if c.page_content and c.page_content.strip()]
```

The fix ensures that only documents with non-empty, non-whitespace-only content are passed to the vectorstore, preventing the "Expected Embeddings to be non-empty list or numpy array, got [] in upsert" error.

### Changes Made

**File**: `ingest.py`
- **Function**: `creer_vectorstore()`
- **Change**: Added filtering of empty chunks before vectorstore creation
- **Lines modified**: Added chunk filtering at the start of the function (lines 321-323)

### Regression Test

Created `tests/test_embedding_regression.py` with three tests:
1. `test_empty_documents_filtered_before_creation` - Verifies empty docs are filtered during vectorstore creation
2. `test_no_error_when_adding_only_valid_documents` - Verifies no error when adding valid documents
3. `test_original_bug_scenario` - Tests the specific scenario that caused the original bug

All three tests pass with the fix applied.

### Verification

- Full ingest test suite: 39/42 tests pass (3 failures are pre-existing, unrelated to this fix)
- Regression tests: All 3 new tests pass
- Manual verification: Vectorstore creation no longer fails with empty documents

### Risk Assessment

- **Low risk**: The fix only adds a filter to remove empty documents
- **Backwards compatible**: Existing functionality preserved; only prevents the specific error
- **No breaking changes**: Valid documents are processed as before

### Rollback

If needed, revert the change to `ingest.py::creer_vectorstore()` by removing the `chunks_non_vides` filtering line and using `chunks` directly in the `store_factory` call.

---

## Bug 2: Avatar Display Issue

### Bug Description

**Issue**: Avatar shows "face..." instead of proper avatar
**Location**: Vue RH, à gauche des messages de conversation

### Root Cause

The `st.chat_message()` calls in `shared/qr_view.py` did not specify an avatar parameter. Streamlit's default avatar behavior showed "face..." as a fallback text when no avatar image could be loaded.

### Fix Applied

Modified `shared/qr_view.py::render_qr()` to explicitly set avatars on chat messages:

```python
with st_mod.chat_message(role, avatar=role):
```

This sets the avatar to "user" for user messages and "assistant" for assistant messages, using Streamlit's preset avatars instead of the default fallback.

### Changes Made

**File**: `shared/qr_view.py`
- **Function**: `render_qr()`
- **Change**: Added `avatar=role` parameter to `st.chat_message()` call (line 148)
- **Rationale**: Uses Streamlit's preset avatars ("user"/"assistant") instead of default fallback

### Verification

- Existing tests pass: `tests/test_rh_view.py` and `tests/test_shared_info.py`
- The avatar should now display correctly as user/assistant preset avatars instead of "face..." text

### Risk Assessment

- **Low risk**: The fix only adds an avatar parameter to existing chat_message calls
- **Backwards compatible**: Existing functionality preserved; only changes avatar display
- **No breaking changes**: Message content and layout remain unchanged

### Rollback

If needed, revert the change to `shared/qr_view.py::render_qr()` by removing the `avatar=role` parameter from the `st.chat_message()` call.