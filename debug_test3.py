import traceback
from fastapi.testclient import TestClient
from backend.app import dependencies
from backend.app.cache.client import CacheClient
from backend.app.providers.demo import DemoProvider
from backend.app.providers.registry import ProviderRegistry
from backend.app.resilience.circuit_breaker import CircuitBreaker

POLYGON = {"type": "Polygon", "coordinates": [[[30.0,50.0],[30.1,50.0],[30.1,50.1],[30.0,50.1],[30.0,50.0]]]}

reg = ProviderRegistry()
reg.register(DemoProvider())
dependencies.set_registry(reg)
dependencies.set_cache(CacheClient())
dependencies.set_breaker(CircuitBreaker())

from backend.app.main import app
client = TestClient(app, raise_server_exceptions=True)

try:
    r = client.post("/api/analyze", json={"geometry": POLYGON, "start_date": "2026-03-01", "end_date": "2026-03-28", "provider": "demo"})
    print(f"Status: {r.status_code}")
except Exception as e:
    print(f"Exception type: {type(e).__name__}")
    print(f"Exception: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
