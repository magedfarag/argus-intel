# Wave 3 Agent Task Card - P1-4 APP_MODE Feature Flag

**Task ID**: P1-4  
**Wave**: 3 of 3  
**Status**: PRE-STAGED  
**Estimated Time**: 30 minutes  
**Complexity**: Medium  

---

## Preconditions (MUST verify before starting)

```bash
# Check P1-3 is merged
git log --oneline main | grep "P1-3\|rasterio"
# Should show P1-3 commit

# Verify local is in sync
git status
# Should show "Your branch is up to date with 'origin/main'"

# Verify P1-4 branch exists
git branch -r | grep "feature/P1-4-app-mode"
# Should output: remotes/origin/feature/P1-4-app-mode
```

**If any precondition fails**: Stop. Request that P1-3 be merged first via PR #5.

---

## Task Scope

This task adds an **APP_MODE feature flag** to allow operating the system in 3 distinct modes:

1. **demo**: Always use DemoProvider (no live imagery)
2. **staging**: Sentinel2 → Landsat → Demo (fallback chain, safe default)
3. **production**: Sentinel2 → Landsat (fail-fast, no fallback)

### Requirements (from HANDOVER.md § 8.2)

- [ ] Add `AppMode` enum to `backend/app/config.py`
- [ ] Enum values: `DEMO`, `STAGING`, `PRODUCTION`
- [ ] Set default: `STAGING` (safe for most deployments)
- [ ] Update `ProviderRegistry.select_provider()` to respect APP_MODE
- [ ] Add APP_MODE to `/api/health` response
- [ ] Implement mode switching in ProviderRegistry
- [ ] Add 12+ unit tests for mode behavior
- [ ] Update `.env.example` with APP_MODE documentation
- [ ] Create PR with full context

---

## Execution Steps

### Step 1: Checkout Feature Branch

```bash
cd d:\Projects\construction-monitor-demo

git fetch origin
git checkout feature/P1-4-app-mode

# Verify you're on the right branch
git branch
# Should show: * feature/P1-4-app-mode (or similar)
```

### Step 2: Create AppMode Enum in config.py

**File**: `backend/app/config.py`

**Add at top** (after imports, before AppSettings class):

```python
from enum import Enum

class AppMode(str, Enum):
    """Application operating mode.
    
    - DEMO: Always use DemoProvider (for testing, no live data)
    - STAGING: Sentinel2 → Landsat → Demo fallback (safe default)
    - PRODUCTION: Sentinel2 → Landsat only (no demo fallback, fail-fast)
    """
    DEMO = "demo"
    STAGING = "staging"
    PRODUCTION = "production"
```

### Step 3: Add app_mode to AppSettings

**In AppSettings class** (around line 50-70), add:

```python
app_mode: AppMode = Field(
    default=AppMode.STAGING,
    description="Operating mode: demo (always demo), staging (sentinel→landsat→demo), production (sentinel→landsat only)",
)
```

**Validation** (add to model_validator):

```python
@model_validator(mode="after")
def validate_mode_constraints(self) -> AppSettings:
    """Validate mode-specific constraints."""
    if self.app_mode == AppMode.PRODUCTION:
        # In production mode, both providers should ideally be configured
        # (but don't enforce - allow graceful degradation)
        pass
    return self
```

### Step 4: Update ProviderRegistry

**File**: `backend/app/providers/registry.py`

**Modify** `select_provider()` method to respect APP_MODE:

```python
def select_provider(self, mode: AppMode) -> BaseImageryProvider:
    """Select provider based on APP_MODE.
    
    Args:
        mode: Application mode (demo/staging/production)
    
    Returns:
        Selected provider instance
    
    Priority chains:
        - demo: [demo]
        - staging: [sentinel2, landsat, demo]
        - production: [sentinel2, landsat]
    """
    if mode == AppMode.DEMO:
        # Always demo
        return self.get_provider("demo")
    
    elif mode == AppMode.STAGING:
        # Try real providers, fallback to demo
        for name in ["sentinel2", "landsat", "demo"]:
            provider = self.get_provider(name)
            if provider and self.is_available(name):
                return provider
        # Final fallback
        return self.get_provider("demo")
    
    elif mode == AppMode.PRODUCTION:
        # Real providers only, no demo fallback
        for name in ["sentinel2", "landsat"]:
            provider = self.get_provider(name)
            if provider and self.is_available(name):
                return provider
        # If no real providers available, raise error
        raise RuntimeError("No real providers available in production mode")
    
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

### Step 5: Update Health Endpoint

**File**: `backend/app/routers/health.py`

**In health() function**, add mode to response:

```python
# Already have AppSettings dependency
# Just add it to response creation:

return HealthResponse(
    status="ok",
    mode=str(settings.app_mode.value),  # ← Add this line
    redis=...,
    celery_worker=...,
    providers=...,
)
```

### Step 6: Write Unit Tests

**File**: `tests/unit/test_config.py` (add to existing file)

Add these test functions:

```python
import pytest
from backend.app.config import AppMode, AppSettings

class TestAppMode:
    """APP_MODE feature flag tests."""
    
    def test_app_mode_enum_values(self):
        """Test APP_MODE enum has correct values."""
        assert AppMode.DEMO.value == "demo"
        assert AppMode.STAGING.value == "staging"
        assert AppMode.PRODUCTION.value == "production"
    
    def test_app_mode_default_is_staging(self):
        """Test default mode is STAGING (safe)."""
        settings = AppSettings(redis_url="")
        assert settings.app_mode == AppMode.STAGING
    
    def test_app_mode_from_env(self):
        """Test APP_MODE can be set via environment."""
        # This tests that the Pydantic model reads from env
        settings = AppSettings(app_mode="production", redis_url="")
        assert settings.app_mode == AppMode.PRODUCTION
    
    def test_app_mode_invalid_raises_validation_error(self):
        """Test invalid APP_MODE raises error."""
        with pytest.raises(ValueError):
            AppSettings(app_mode="invalid", redis_url="")
    
    def test_demo_mode_always_demo(self, demo_registry):
        """Test demo mode always returns demo provider."""
        demo_settings = AppSettings(app_mode="demo", redis_url="")
        provider = demo_registry.select_provider(demo_settings.app_mode)
        assert provider.provider_name == "demo"
    
    def test_staging_mode_tries_real_then_demo(self, demo_registry):
        """Test staging mode tries sentinel2→landsat→demo."""
        staging_settings = AppSettings(app_mode="staging", redis_url="")
        provider = demo_registry.select_provider(staging_settings.app_mode)
        # Should get demo (real providers not available in test)
        assert provider.provider_name == "demo"
    
    def test_production_mode_fails_without_real_providers(self, demo_registry):
        """Test production mode raises if no real providers available."""
        prod_settings = AppSettings(app_mode="production", redis_url="")
        with pytest.raises(RuntimeError, match="No real providers available"):
            demo_registry.select_provider(prod_settings.app_mode)
    
    def test_health_endpoint_includes_mode(self, app_client):
        """Test /api/health includes current app_mode."""
        response = app_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ["demo", "staging", "production"]
```

### Step 7: Update .env.example

**File**: `.env.example`

**Add this section**:

```bash
# APP_MODE: Operating mode
#   - demo: Always use DemoProvider (testing only, no live imagery)
#   - staging: Real providers with demo fallback (recommended for most deployments)
#   - production: Real providers only, fail-fast if unavailable
# Default: staging (safe for most use cases)
APP_MODE=staging
```

### Step 8: Run Tests

```bash
# Run just the APP_MODE tests
python -m pytest tests/unit/test_config.py::TestAppMode -v

# Run all config tests
python -m pytest tests/unit/test_config.py -v

# Full test suite
python -m pytest tests/ --tb=short -q
```

**Expected**:
- All APP_MODE tests pass
- No regressions in existing tests
- Total: 120+ tests passing

### Step 9: Commit and Create PR

```bash
git add backend/app/config.py
git add backend/app/providers/registry.py
git add backend/app/routers/health.py
git add tests/unit/test_config.py
git add .env.example

git commit -m "feat(P1-4): Add APP_MODE feature flag (demo/staging/production)"

git push origin feature/P1-4-app-mode
```

**Create PR** on GitHub:
- Title: "P1-4: APP_MODE feature flag for operational modes (Wave 3)"
- Base: `main`
- Head: `feature/P1-4-app-mode`
- Description: Copy from TASK_COMPLETION_REPORT.md § P1-4

---

## Success Criteria (ALL must pass)

- [x] AppMode enum defined with 3 values (already planned)
- [ ] Default is STAGING
- [ ] ProviderRegistry.select_provider() respects mode
- [ ] /api/health returns current mode
- [ ] 12+ unit tests all passing
- [ ] .env.example documents APP_MODE
- [ ] No regressions (all existing tests still pass)
- [ ] PR created with full context

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| `AppMode` not found in imports | Verify you added it to `backend/app/config.py` before AppSettings |
| `ProviderRegistry.select_provider()` signature wrong | Check method takes `mode: AppMode` parameter |
| Tests fail with "No real providers" | This is expected in test environment with demo_registry fixture. Don't change test, ensure it raises RuntimeError |
| Health endpoint doesn't return mode | Verify you added `mode=str(settings.app_mode.value)` to HealthResponse |
| Import errors | Verify all imports at top of files: `from enum import Enum`, `from backend.app.config import AppMode` |

---

## Deliverable Checklist

By end of this task:

- [ ] AppMode enum implemented in config.py
- [ ] ProviderRegistry updated with mode-based selection
- [ ] Health endpoint returns APP_MODE
- [ ] 12+ unit tests written and passing
- [ ] .env.example updated with APP_MODE docs
- [ ] All 120+ tests passing (no regressions)
- [ ] PR #6 created and ready for merge
- [ ] Full context documented in PR description

---

## What Happens After

After P1-4 merges:

1. System can be deployed in 3 modes
2. Default (staging) allows live data with safe fallback
3. Production mode enforces real providers only
4. Demo mode guarantees consistent test data

---

## Questions?

Refer to:
- `.github/TASK_COMPLETION_REPORT.md` - Full context
- `.github/ORCHESTRATION_STATUS.md` - Dependencies and workflow
- `docs/ARCHITECTURE.md` - System design
- PR descriptions from P1-1, P3-7, P3-8 - Pattern examples
