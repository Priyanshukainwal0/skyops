# ⚡ SkyOps — Production-Grade DevOps Platform

[![CI](https://github.com/Priyanshukainwal0/skyops/actions/workflows/ci.yml/badge.svg)](https://github.com/Priyanshukainwal0/skyops/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-46E3B7?logo=render)](https://skyops-api-8dn9.onrender.com)
[![Helm Chart](https://img.shields.io/badge/Helm-v3-0F1689?logo=helm)](./helm/skyops)
[![License](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)

> A **complete 6-phase DevOps pipeline** built from scratch — containerised microservices, Kubernetes orchestration, Helm charts, automated CI/CD, a full observability stack (Prometheus + Grafana), and live cloud deployment with a persistent database.

**Live dashboard →** https://skyops-api-8dn9.onrender.com  
**Companion app (TicketDesk) →** https://ticketdesk-app.onrender.com  
**API docs →** https://skyops-api-8dn9.onrender.com/docs

---

## 🗺️ What Was Built (6 Phases)

| Phase | Skill | What Was Done |
|-------|-------|---------------|
| **1** | 🐳 Docker Compose | Multi-service stack with api-gateway + monitor-worker, bridge networking, health checks |
| **2** | ☸️ Kubernetes | Full K8s manifests — Deployments, Services, ConfigMaps, HPA, Ingress, Namespace |
| **3** | ⚙️ GitHub Actions | CI pipeline: lint → pytest → docker build → push to Docker Hub (Run #3 ✓ green) |
| **4** | ⛵ Helm | Custom Helm chart with templating, values.yaml overrides, sub-chart dependencies |
| **5** | 📊 Prometheus + Grafana | Full observability via Helm sub-charts, PromQL dashboards, auto-provisioned ConfigMap |
| **6** | ☁️ Render + Neon | Live cloud deployment, Neon PostgreSQL (persistent, free), render.yaml Blueprint IaC |

---

## 🏗️ Architecture

```
Developer Machine
     │
     │  git push
     ▼
  GitHub ──────────────────────────► GitHub Actions CI
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                         pytest ✓               docker build + push
                              │                         │
                              └────────────┬────────────┘
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                    k3d (Local Cluster)          Render (Production)
                         │                             │
                   Helm chart                    api-gateway
                  ┌──────┴──────┐                Docker container
                  │             │                     │
             Prometheus      Grafana           Neon PostgreSQL
             (metrics)     (dashboards)       (persistent DB)
                  │                                   │
             api-gateway ◄────── scrapes ──── /metrics endpoint
             (FastAPI)                                │
                  │                           monitors TicketDesk
             SQLite (dev)                    https://ticketdesk-app.onrender.com
```

---

## 📁 Project Structure

```
skyops/
├── api-gateway/               # Core FastAPI service
│   ├── app/
│   │   ├── main.py            # API routes, background checker, dual DB support
│   │   └── static/
│   │       └── index.html     # Live portfolio dashboard (Chart.js, dark UI)
│   ├── tests/                 # pytest suite
│   ├── Dockerfile             # Multi-stage Docker build
│   └── requirements.txt
│
├── monitor-worker/            # Standalone health-check worker (Phase 1-2)
│   ├── worker.py
│   └── Dockerfile
│
├── k8s/                       # Phase 2 — Kubernetes manifests
│   ├── namespace.yaml
│   ├── api-gateway.yaml       # Deployment + Service
│   ├── monitor-worker.yaml
│   ├── configmap.yaml
│   ├── ingress.yaml
│   └── hpa.yaml               # Horizontal Pod Autoscaler
│
├── helm/skyops/               # Phase 4 — Helm chart
│   ├── Chart.yaml             # Chart metadata + sub-chart deps
│   ├── values.yaml            # All config (prometheus, grafana, services)
│   └── templates/
│       ├── _helpers.tpl
│       ├── namespace.yaml
│       ├── api-gateway.yaml
│       ├── configmap.yaml
│       ├── ingress.yaml
│       ├── hpa.yaml
│       └── grafana-dashboard.yaml   # Auto-provisioned Grafana dashboard
│
├── .github/
│   └── workflows/
│       └── ci.yml             # Phase 3 — GitHub Actions CI pipeline
│
├── docker-compose.yml         # Phase 1 — local dev stack
└── render.yaml                # Phase 6 — Render Blueprint (IaC)
```

---

## 🚀 Quick Start

### Option A — Docker Compose (local dev)

```bash
git clone https://github.com/Priyanshukainwal0/skyops.git
cd skyops

docker compose up --build

# Dashboard
open http://localhost:8000

# API docs
open http://localhost:8000/docs
```

### Option B — Kubernetes with k3d (Phase 2)

```bash
# Create cluster
k3d cluster create skyops-cluster --port "8080:80@loadbalancer"

# Apply all manifests
kubectl apply -f k8s/

# Verify
kubectl get all -n skyops
```

### Option C — Helm (Phase 4 + 5)

```bash
# Add chart repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install sub-chart dependencies
helm dependency update ./helm/skyops

# Install the chart
helm install skyops ./helm/skyops -n skyops --create-namespace

# Port-forward Grafana
kubectl port-forward svc/skyops-grafana 3000:80 -n skyops
# open http://localhost:3000  (admin / skyops-admin)
```

---

## ⚙️ CI/CD Pipeline (Phase 3)

Every push to `main` runs this GitHub Actions pipeline:

```
push to main
    │
    ├─ Checkout + Python setup
    ├─ pip install dependencies
    ├─ flake8 lint
    ├─ pytest (tests/)                ← Run #3 ✓ passing
    ├─ docker build api-gateway
    ├─ docker push → Docker Hub
    └─ (Render auto-deploy triggered by git push)
```

Workflow file: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

---

## 📊 Observability Stack (Phase 5)

Prometheus and Grafana are deployed as Helm sub-chart dependencies.

**Grafana dashboard panels:**
- Total HTTP Requests (counter)
- Error Rate 5xx (percentage)
- Avg Request Latency (histogram)
- API Gateway Replicas (gauge)
- Request Rate by Endpoint (time series)
- P95 Latency by Endpoint (time series)
- HTTP Status Codes Over Time (bar chart)

**Prometheus scrape config** (in `values.yaml`):
```yaml
prometheus:
  extraScrapeConfigs: |
    - job_name: skyops-api-gateway
      static_configs:
        - targets: ['api-gateway.skyops.svc.cluster.local:8000']
      metrics_path: /metrics
      scrape_interval: 15s
```

Dashboard is auto-provisioned via ConfigMap — no manual import needed.

---

## ☁️ Live Deployment (Phase 6)

| Component | Platform | URL |
|-----------|----------|-----|
| api-gateway | Render (Docker) | https://skyops-api-8dn9.onrender.com |
| Dashboard | Render (static) | https://skyops-api-8dn9.onrender.com |
| Database | Neon PostgreSQL | Free tier, permanent, no expiry |
| TicketDesk | Render (Python) | https://ticketdesk-app.onrender.com |

Deployment is managed via [`render.yaml`](./render.yaml) Blueprint — infrastructure as code.  
Auto-deploys on every `git push` to `main`.

**Why Neon instead of Render PostgreSQL?**  
Render's free PostgreSQL expires after 90 days. Neon is free forever with no expiry, making it the right choice for a persistent portfolio project.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Live dashboard (HTML) |
| `GET` | `/health` | Liveness probe |
| `GET` | `/metrics` | Prometheus metrics endpoint |
| `POST` | `/api/services` | Register a service to monitor |
| `GET` | `/api/services` | List all services + last status |
| `DELETE` | `/api/services/{id}` | Remove a service |
| `GET` | `/api/checks/{service_id}` | Get check history (last 50) |
| `POST` | `/api/run-checks` | Manually trigger checks now |

Full interactive docs: https://skyops-api-8dn9.onrender.com/docs

---

## 🛠️ Technology Stack

| Category | Technology |
|----------|-----------|
| Backend | FastAPI, Python 3.11, uvicorn |
| Containerisation | Docker, Docker Compose |
| Orchestration | Kubernetes (k3d), kubectl |
| Package Manager | Helm v3 |
| CI/CD | GitHub Actions |
| Metrics | Prometheus, prometheus-fastapi-instrumentator |
| Dashboards | Grafana (auto-provisioned) |
| Database | PostgreSQL (Neon) / SQLite (local) |
| Cloud | Render (Docker runtime) |
| IaC | render.yaml Blueprint |
| Testing | pytest |
| Frontend | Vanilla JS, Chart.js, dark UI |

---

## 🧪 Running Tests

```bash
cd api-gateway
pip install -r requirements.txt
pytest tests/ -v
```

---

## 🌱 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(empty)* | PostgreSQL URL — if set, uses Postgres instead of SQLite |
| `CHECK_INTERVAL` | `60` | Seconds between background health checks |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout per check (seconds) |
| `DEFAULT_SERVICES` | *(empty)* | Auto-seed: `"Name\|URL,Name2\|URL2"` |

---

## 👤 Author

**Priyanshu Kainwal**  
DevOps Portfolio Project — SkyOps Platform

[![Live](https://img.shields.io/badge/Live%20Demo-open-46E3B7)](https://skyops-api-8dn9.onrender.com)
[![GitHub](https://img.shields.io/badge/GitHub-Priyanshukainwal0-181717?logo=github)](https://github.com/Priyanshukainwal0)
