# Deployment Guide — Construction Activity Monitor v2.0

**Last Updated**: 2026-03-28  
**Production Ready**: Yes (with security hardening checklist completed)

---

## **1. Prerequisites**

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.11+ | Dataclasses frozen, type hints |
| Docker | 24.0+ | Multi-stage builds |
| Docker Compose | 2.20+ | For local/staging |
| Redis | 7.0+ | For cache & Celery broker |
| GDAL/libgdal | 3.4+ | For rasterio; installed in Dockerfile |
| Git | 2.30+ | For GitHub integration |

---

## **2. Deployment Scenarios**

### **2.1 Local Development (Demo Mode)**

**No Redis, no credentials required**. Ideal for feature development and prototyping.

```bash
git clone https://github.com/magedfarag/construction-monitor-demo
cd construction-monitor-demo

python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt

# Run with auto-reload (hot changes)
uvicorn app.main:app --reload

# Open http://127.0.0.1:8000
```

**Demo mode behavior**:
- `APP_MODE=auto` (default)
- No Redis configured → in-memory cache only
- No Sentinel-2 credentials → auto-fallback to Landsat/demo
- Celery unavailable → sync execution only

**Coverage**: All endpoints work; analysis returns curated demo results.

---

### **2.2 Local Development with Redis + Async**

**For testing async job pipeline and real caching**.

```powershell
# Terminal 1: Start Redis container
docker run --name redis-dev -p 6379:6379 -d redis:7-alpine

# Terminal 2: API server with auto-reload
$env:REDIS_URL = "redis://localhost:6379/0"
$env:APP_MODE = "auto"
$env:LOG_FORMAT = "text"  # Human-readable logs

uvicorn app.main:app --reload

# Terminal 3: Celery worker (background tasks)
$env:REDIS_URL = "redis://localhost:6379/0"

celery -A app.workers.celery_app.celery_app worker `
    --loglevel=info `
    --pool=solo `
    --concurrency=2 `
    --task-events
```

**Test async job submission**:
```bash
# Terminal 4: Submit a job
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {"type": "Polygon", "coordinates": [[[30, 50], [30.1, 50], [30.1, 50.1], [30, 50.1], [30, 50]]]},
    "start_date": "2026-03-27",
    "end_date": "2026-03-28",
    "async_execution": true
  }'

# Response: {"job_id": "job-...", "state": "pending", ...}

# Poll status
curl http://localhost:8000/api/jobs/job-XXXXX
```

---

### **2.3 Docker Compose (Staging / Production)**

**Recommended** for integrated testing with all services.

#### **Step 1: Create .env**

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# ──────────────────────────────────────────────────────────────
# App behavior
# ──────────────────────────────────────────────────────────────
APP_MODE=live                    # auto / live / demo
LOG_LEVEL=INFO                   # DEBUG / INFO / WARNING / ERROR
LOG_FORMAT=json                  # json / text

# ──────────────────────────────────────────────────────────────
# CORS & Security (P1-5 & P1-6)
# ──────────────────────────────────────────────────────────────
ALLOWED_ORIGINS=https://myapp.com,https://api.myapp.com
API_KEY=your-strong-api-key     # Generate: openssl rand -hex 32

# ──────────────────────────────────────────────────────────────
# Infrastructure
# ──────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0  # In Docker: redis service name

# ──────────────────────────────────────────────────────────────
# Sentinel-2 (optional; required for app_mode=live)
# ──────────────────────────────────────────────────────────────
SENTINEL2_CLIENT_ID=...         # Get from: https://dataspace.copernicus.eu
SENTINEL2_CLIENT_SECRET=...

# ──────────────────────────────────────────────────────────────
# Caching & resilience
# ──────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS=3600          # 1 hour
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
```

#### **Step 2: Start Services**

```bash
# Build images and start all services in background
docker compose up --build -d

# Verify all running
docker compose ps

# Watch logs
docker compose logs -f api           # API server
docker compose logs -f worker        # Celery worker
docker compose logs -f redis         # Redis
```

#### **Step 3: Health Check**

```bash
# API health
curl http://localhost:8000/api/health

# Expected response:
# {"status": "ok", "mode": "live", "redis": "healthy", ...}

# Check providers
curl http://localhost:8000/api/providers
```

#### **Step 4: Stop Services**

```bash
docker compose down

# Remove volumes (WARNING: deletes data)
docker compose down -v
```

---

### **2.4 Kubernetes Deployment**

For cloud-scale deployments (AWS EKS, GCP GKE, Azure AKS, or self-hosted).

#### **2.4.1 Building the image**

```bash
# Build and push to your registry
docker build -t myregistry.azurecr.io/construction-monitor:v2.0.0 .
docker push myregistry.azurecr.io/construction-monitor:v2.0.0
```

#### **2.4.2 Kubernetes manifests**

Create `kubernetes/` directory with deployment manifests:

```yaml
# kubernetes/redis-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
  type: ClusterIP
```

```yaml
# kubernetes/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: construction-monitor-api
spec:
  replicas: 3                           # Horizontal scaling
  selector:
    matchLabels:
      app: construction-monitor
      component: api
  template:
    metadata:
      labels:
        app: construction-monitor
        component: api
    spec:
      containers:
      - name: api
        image: myregistry.azurecr.io/construction-monitor:v2.0.0
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: "redis://redis:6379/0"
        - name: APP_MODE
          value: "live"
        - name: LOG_FORMAT
          value: "json"
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: api-key
        - name: SENTINEL2_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: sentinel2-client-id
        - name: SENTINEL2_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: sentinel2-client-secret
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/config
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: construction-monitor-api
spec:
  selector:
    app: construction-monitor
    component: api
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
  type: LoadBalancer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: construction-monitor-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: construction-monitor
      component: worker
  template:
    metadata:
      labels:
        app: construction-monitor
        component: worker
    spec:
      containers:
      - name: worker
        image: myregistry.azurecr.io/construction-monitor:v2.0.0
        command: ["celery", "-A", "app.workers.celery_app.celery_app", "worker", "--loglevel=info"]
        env:
        - name: REDIS_URL
          value: "redis://redis:6379/0"
        - name: LOG_FORMAT
          value: "json"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

**Deploy to cluster**:
```bash
kubectl create namespace construction-monitor
kubectl create secret generic app-secrets \
  --from-literal=api-key=<YOUR-API-KEY> \
  --from-literal=sentinel2-client-id=<CLIENT-ID> \
  --from-literal=sentinel2-client-secret=<CLIENT-SECRET> \
  -n construction-monitor
kubectl apply -f kubernetes/ -n construction-monitor
kubectl get pods -n construction-monitor
```

---

## **3. Environment Variables Reference**

### **Core Settings**

| Variable | Default | Production Value | Notes |
|----------|---------|------------------|-------|
| `APP_MODE` | `auto` | `live` | Fail-fast if no live provider available |
| `LOG_LEVEL` | `INFO` | `WARNING` | Reduce log volume |
| `LOG_FORMAT` | `json` | `json` | Machine-readable for log aggregation |

### **Security (P1-5, P1-6)**

| Variable | Default | Production Value | Notes |
|----------|---------|------------------|-------|
| `ALLOWED_ORIGINS` | `http://localhost:3000,…` | Your domains | Comma-separated CORS origins |
| `API_KEY` | `` (empty) | `openssl rand -hex 32` | Strong random 64-char hex string |

### **Infrastructure**

| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_URL` | `` | Format: `redis://[user:password@]host:port/db` |
| `HTTP_TIMEOUT_SECONDS` | `30` | Provider request timeout |
| `HTTP_MAX_RETRIES` | `3` | Transient error retry count |

### **Sentinel-2 (Copernicus)**

| Variable | Required | Notes |
|----------|----------|-------|
| `SENTINEL2_CLIENT_ID` | If `APP_MODE=live` | OAuth2 client ID |
| `SENTINEL2_CLIENT_SECRET` | If `APP_MODE=live` | OAuth2 client secret |

---

## **4. Advanced Configuration**

### **4.1 Redis with TLS**

```bash
REDIS_URL=rediss://user:password@myredis.cache.redis.io:6380/0
#                ^ 'rediss' = TLS
```

### **4.2 Reverse Proxy (Nginx)**

Place behind reverse proxy for HTTPS, load balancing, compression.

### **4.3 Kubernetes Health Probes**

- **Liveness**: `GET /api/health` (restart if fails)
- **Readiness**: `GET /api/config` (remove from load balancer if fails)

---

## **5. Production Hardening Checklist**

### **Security**
- [ ] Set `APP_MODE=live` (fail-fast mode)
- [ ] Configure `ALLOWED_ORIGINS` for your domain
- [ ] Generate strong `API_KEY` (`openssl rand -hex 32`)
- [ ] Use TLS for Redis (`rediss://`)
- [ ] Run `pip-audit` in CI

### **Reliability**
- [ ] Enable Kubernetes health probes
- [ ] Configure horizontal pod autoscaling
- [ ] Set resource limits (requests + limits)
- [ ] Enable circuit breaker

### **Performance**
- [ ] Set `CACHE_TTL_SECONDS` per SLA
- [ ] Configure `ASYNC_AREA_THRESHOLD_KM2`
- [ ] Use CDN for static assets
- [ ] Enable response compression

### **Observability**
- [ ] Enable JSON logging
- [ ] Set up dashboards (Prometheus + Grafana)
- [ ] Configure alerts (error rate, latency, providers)
- [ ] Retain logs 30+ days

---

## **6. Troubleshooting**

### **Redis Connection Error**
```
ConnectionError: Error 11001 getaddrinfo failed
```
- Verify Redis running: `docker ps | grep redis`
- Check `REDIS_URL` in `.env`
- Test: `redis-cli -h localhost ping`

### **Sentinel-2 OAuth2 Failure**
```
HTTPStatusError: 401 Unauthorized
```
- Verify credentials at https://dataspace.copernicus.eu
- Check `SENTINEL2_CLIENT_ID`, `SENTINEL2_CLIENT_SECRET`
- Test manually with curl

### **Rate Limit (429) Errors**
- You're hitting `5/minute` on `/api/analyze`
- Wait 60 seconds before retrying
- Distribute across multiple API keys

---

## **7. Support**

For issues: https://github.com/magedfarag/construction-monitor-demo/issues
