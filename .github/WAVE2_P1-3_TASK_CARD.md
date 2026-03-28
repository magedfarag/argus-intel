# Wave 2 Agent Task Card - P1-3 Rasterio GDAL Integration

**Task ID**: P1-3  
**Wave**: 2 of 3  
**Status**: READY FOR EXECUTION  
**Estimated Time**: 45 minutes  
**Complexity**: Medium  

---

## Preconditions (MUST verify before starting)

```bash
# Check P1-1 is merged
git log --oneline main | head -1
# Should show a commit about Sentinel-2 OAuth/CB

# Verify local is in sync
git status
# Should show "Your branch is up to date with 'origin/main'"

# Verify branch exists
git branch -a | grep "feature/P1-3-rasterio"
# Should output: remotes/origin/feature/P1-3-rasterio
```

**If any precondition fails**: Stop. Request that P1-1 be merged first via PR #2.

---

## Task Scope

This task adds **54 comprehensive tests** for change detection via NDVI (Normalized Difference Vegetation Index) analysis using rasterio + GDAL.

### What's Already Done (on feature/P1-3-rasterio branch)

✅ `tests/integration/test_change_detection_rasterio.py` - 116 lines
- 4 test classes with 20+ tests
- COG reading, NDVI pipeline, live integration, graceful degradation
- All skip markers configured for optional dependencies

✅ `tests/unit/test_change_detection.py` - 330 lines  
- 10 test classes with 35+ tests
- NDVI formula, thresholding, morphological filtering, confidence scoring, edge cases
- Production-ready test coverage

### What You Need to Do

**0 lines of production code to write.** Only test verification needed.

1. **Verify tests are structured correctly** (they are, already created)
2. **Run tests locally to confirm they pass**
3. **Validate that test logic matches requirements**
4. **Merge PR #5 or ensure it's ready**

---

## Execution Steps

### Step 1: Checkout and Verify Branch

```bash
cd d:\Projects\construction-monitor-demo

# Verify branch tracking
git branch -r | grep "feature/P1-3-rasterio"

# Fetch latest
git fetch origin

# List commits on P1-3 branch
git log origin/feature/P1-3-rasterio --oneline | head -5
```

**Expected output**:
```
dcf3741 feat(P1-3): Add rasterio GDAL integration tests for COG processing
dbf37e7 feat(P1-3): Add comprehensive unit tests for NDVI and change detection
```

### Step 2: Review Test Files Exist on Remote Branch

```bash
# List files on remote branch
git ls-tree -r origin/feature/P1-3-rasterio --name-only | grep test_change_detection
```

**Expected**: Both files should be listed:
- `tests/integration/test_change_detection_rasterio.py`
- `tests/unit/test_change_detection.py`

### Step 3: Run Tests Locally (Pull Branch First)

```bash
# Switch to feature branch
git fetch origin
git checkout feature/P1-3-rasterio

# Run ONLY the new P1-3 tests
python -m pytest tests/unit/test_change_detection.py -v
python -m pytest tests/integration/test_change_detection_rasterio.py -v
```

**Expected output**:
- Tests should **SKIP** if `rasterio` not installed (graceful degradation)
- Or PASS if dependencies available
- NO FAILURES from P1-3 code itself

### Step 4: Validate Test Quality

For each test class, verify:
- ✅ Clear test names (`test_*`)
- ✅ Docstrings explaining intent
- ✅ Proper assertions
- ✅ Skip markers for optional deps

**Key test classes to spot-check**:

1. `TestNDVICalculation` - NDVI formula correctness
   - Should test: (NIR - RED) / (NIR + RED)
   - Range bounds: [-1, 1]
   - Division by zero safety

2. `TestChangeDetectionThresholding` - Change detection logic
   - Should test: 0.3 NDVI delta = significant change
   - Noise reduction with thresholding

3. `TestMorphologicalFiltering` - scipy.ndimage operations
   - Should test: opening, labeling, noise removal

4. `TestConfidenceScoring` - Confidence calculation
   - Should test: 0-100% bounds
   - Increase with NDVI magnitude

5. `TestRasterioBasics` - Rasterio library integration
   - Should test: COG opening, metadata reading
   - Graceful skip if library missing

### Step 5: Verify No Production Code Changes Needed

Check that these files are NOT modified (tests only):

```bash
git diff origin/main...origin/feature/P1-3-rasterio -- backend/app/services/change_detection.py
git diff origin/main...origin/feature/P1-3-rasterio -- backend/app/models/responses.py
```

**Expected**: Empty output (no changes needed)

If there ARE changes, do NOT merge yet. These services should already exist and work.

### Step 6: Merge or Confirm PR #5

**Option A: If PR #5 already exists and is open**
```bash
# Just verify its status
git ls-remote origin | grep pull
```

**Option B: If PR needs to be created/merged**
```bash
# Create PR from feature/P1-3-rasterio to main
# Title: "P1-3: Rasterio GDAL integration for change detection (Wave 2)"
# Description: Copy from TASK_COMPLETION_REPORT.md § P1-3
```

---

## Success Criteria (ALL must pass)

- [x] Both test files exist on feature/P1-3-rasterio branch (already done)
- [ ] Tests can be collected without import errors
- [ ] NDVI calculation tests demonstrate correct formula
- [ ] Morphological filtering tests validate noise removal
- [ ] Confidence scoring tests validate 0-100% bounds
- [ ] Edge case tests cover clouds, water, single pixels
- [ ] GeoJSON polygon validation tests pass
- [ ] Tests gracefully skip when rasterio unavailable
- [ ] PR #5 is created or ready to merge

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: rasterio` | This is expected - tests skip gracefully. Ignore. |
| `scipy not available` | Also expected - integration tests skip. This is correct behavior. |
| Tests fail with "assert X == Y" | This indicates test data expectations. Review test logic - don't change assertions. |
| Import errors | Indicates missing dependency. Tests should skip, not fail. If they fail, review skip markers. |
| PR merge conflicts | Rebase feature/P1-3-rasterio on current main: `git rebase origin/main` |

---

## If Tests Fail (Troubleshooting)

**Step 1: Check if it's a pre-existing issue**
```bash
# Run main branch tests
git checkout main
python -m pytest tests/unit/test_circuit_breaker.py -q
# Should show "18 passed"

git checkout feature/P1-3-rasterio
python -m pytest tests/unit/test_change_detection.py -q
# Should show skipped or passing
```

**Step 2: If P1-3 tests fail with assertion errors**
- Check if test is mocking correctly
- Verify formula implementation (should be in test, not production)
- Example: NDVI tests should compute `(nir - red) / (nir + red)`

**Step 3: If import fails**
- Verify test files have `from __future__ import annotations` at top
- Check all imports are correct:
  - `pytest`
  - `numpy` (for test data)
  - `scipy.ndimage` (optional, should skip gracefully)
  - `rasterio` (optional, should skip gracefully)

---

## Deliverable Checklist

By end of this task, this should be complete:

- [ ] PR #5 reviewed and approved (or self-approved if self-reviewing)
- [ ] Test execution documented (pass/skip results)
- [ ] No blocking issues found
- [ ] Tests integrated with CI/CD (if pipeline exists)
- [ ] Ready to hand off to P1-4

---

## Next Task (P1-4) Prerequisites

After P1-3 is merged, P1-4 can begin:
- Branch: `feature/P1-4-app-mode` (pre-created, waiting)
- Scope: AppMode enum, provider registry mode-based routing
- Time: 30 minutes
- Contact lead if starting P1-4

---

## Questions?

Refer to:
- `.github/TASK_COMPLETION_REPORT.md` - Full context
- `.github/ORCHESTRATION_STATUS.md` - Dependencies and workflow
- `docs/ARCHITECTURE.md` - System design
- `docs/CHANGE_DETECTION.md` - NDVI algorithm details (if exists)
