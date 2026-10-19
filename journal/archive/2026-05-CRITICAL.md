# Critical Issues - Immediate Fixes Required

This document lists all critical bugs and issues that must be fixed before the project can work correctly.

---

## 🔴 CRITICAL BUGS

### 1. Outdated/Misleading Comments in Task Orchestrator
**File:** `reasoning_sub_agents/task_orchestrator.py` (lines 56-58)

**Issue:** Comment claims decomposer only does step 1, but actually uses `SelfCritiquingDecomposition` which implements steps 1-3.

**Problem Code:**
```python
# decomposer handles steps 1-3
# TODO: just to get running the decomposer is currently only doing step 1
sub_tasks = self.decomposer.generate_sub_tasks(user_input)
```

**Impact:**
- Misleading for developers
- Suggests incomplete implementation when it's actually working
- Could lead to incorrect assumptions about system behavior

**Fix Required:**
Update the comment to reflect reality:
```python
# decomposer handles steps 1-3 (decomposition with self-critique and regeneration)
sub_tasks = self.decomposer.generate_sub_tasks(user_input)
```

---

### 2. Commented Workarounds for Known Bugs
**Files:**
- `reasoning_sub_agents/task_decomposition/simple_decomposition.py` (lines 96-100)
- `reasoning_sub_agents/task_decomposition/self_critique_decomposition.py` (lines 162-164)

**Issue:** Code contains commented-out workarounds for a known bug where single items aren't returned as lists.

**Problem Code:**
```python
# this is a workaround for a known bug where if there is a single item
# returned, it will not be returned as a list
# decompose_response = decompose_response.decompose_items
if not isinstance(decompose_response, list):
    decompose_response = [decompose_response]
```

**Impact:**
- Suggests there's an unresolved bug in the JSON response parsing
- The workaround may not be working correctly
- Could cause issues with single-item responses

**Fix Required:**
- Investigate the root cause in `get_streamed_json_response`
- Ensure it always returns a list for list response models
- Remove the workarounds once the root cause is fixed

---

## 📋 Verification Steps After Fixes

1. **Run all tests:**
   ```bash
   pytest tests/ -v
   ```

2. **Test the complete workflow:**
   ```bash
   python main.py
   ```

3. **Verify imports work:**
   ```python
   from reasoning_sub_agents.executor.simple_executor import SimpleAgentExecutor
   from reasoning_sub_agents.schemas import AccumulatedResult
   ```

4. **Test with a simple prompt:**
   - Ensure decomposition generates multiple sub-tasks
   - Ensure execution completes without errors
   - Ensure synthesis produces a final result

---

## ⚠️ Priority Order

| # | Issue | Impact | Difficulty | Priority |
|---|-------|--------|------------|----------|
| 1 | File name typo | High - breaks imports | Low | **P0 - FIX FIRST** |
| 2 | Broken validator | High - runtime errors | Low | **P0 - FIX FIRST** |
| 3 | Misleading comments | Medium - developer confusion | Low | P1 |
| 4 | Commented workarounds | Medium - potential bugs | Medium | P1 |