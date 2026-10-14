# StockPilot: Inventory Management on AWS EKS

StockPilot is a small inventory management app for a warehouse team. It tracks products (SKU, supplier, location, unit price), how much stock is on hand, and when each item needs reordering. Every stock change (restock, sale, return, damage, correction) is recorded as an audited **stock movement**. The dashboard shows inventory value, low-stock and out-of-stock counts, a "reorder soon" list and a live movement feed.

The DevOps capstone wraps this app in a full delivery pipeline: tests, container images, a security scan, a registry, Terraform-built AWS infrastructure, Helm on Kubernetes, Ingress, autoscaling and monitoring.

```text
 Developer ──git push──▶ GitHub ──▶ GitHub Actions
                                     ├─ pytest (15 tests, SQLite test DB)
                                     ├─ npm run build
                                     ├─ docker build backend + frontend   (tag = commit SHA)
                                     ├─ Trivy scan  (fail on HIGH/CRITICAL)
                                     ├─ push ──▶ ghcr.io/<you>/stockpilot-{backend,frontend}:<sha>
                                     └─ helm upgrade --install ──┐
                                                                 ▼
 Terraform ──▶ AWS ap-south-1: VPC (2 public + 2 private subnets, NAT) ──▶ EKS + managed node group
                                                                 │
             ingress-nginx (NLB) ──/──────▶ frontend  (React + nginx, 2 pods)
                                 └─/api──▶ backend   (FastAPI, 2-6 pods, HPA) ──▶ PostgreSQL (StatefulSet + gp3 EBS)
                                                         │ /metrics
                                     Prometheus ◀────────┘ (ServiceMonitor) ──▶ Grafana dashboard
```

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | React 19, Vite, plain CSS (responsive, dark mode), nginx-unprivileged |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic, prometheus-fastapi-instrumentator |
| Database | PostgreSQL 16 |
| Tests | Pytest with an in-memory SQLite test database (never the real DB) |
| Containers | Docker (non-root images), Docker Compose |
| CI/CD | GitHub Actions, Trivy, GitHub Container Registry |
| Infrastructure | Terraform (`terraform-aws-modules/vpc` + `eks`), AWS VPC, EKS, EBS CSI, metrics-server |
| Kubernetes | Helm chart: Deployments, StatefulSet, Services, Ingress, HPA, PDBs, Secret |
| Observability | kube-prometheus-stack (Prometheus + Grafana), ServiceMonitor, a pre-built dashboard |

## Repository layout

```text
backend/            FastAPI app (app/), Alembic migrations, pytest suite, Dockerfile
frontend/           React app (src/), nginx.conf, multi-stage Dockerfile
docker-compose.yml  Full local stack: postgres + backend + frontend
.github/workflows/  ci-cd.yml (test → build/scan/push → deploy)
terraform/          VPC + EKS (+ EBS CSI, metrics-server add-ons)
k8s/                namespace, gp3 StorageClass, ingress-nginx values
helm/stockpilot/    Helm chart (values.yaml, values-dev.yaml, values-prod.yaml)
monitoring/         kube-prometheus-stack values
troubleshooting/    5 deliberately broken manifests + guide
scripts/            load-test.sh (HPA demo), seed-activity.sh
```

## API

Interactive docs are at **`/api/docs`** (Swagger UI).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check: the process is up |
| GET | `/ready` | Readiness check: the database is reachable (returns 503 otherwise) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/products?search=&category=&stock_status=` | List or filter products |
| GET | `/api/products/stats` | KPI totals: products, units, inventory value, low or out of stock |
| GET | `/api/products/{id}` | Get one product |
| POST | `/api/products` | Create a product (opening stock is recorded as a movement) |
| PUT | `/api/products/{id}` | Partially update product details |
| DELETE | `/api/products/{id}` | Delete a product and its movement history |
| POST | `/api/products/{id}/adjust` | Change stock with a reason (returns 409 if stock would go negative) |
| GET | `/api/movements?limit=` | Recent stock movements (activity feed) |

The database has two tables, `products` and `stock_movements`, created by Alembic migrations `0001` and `0002`. Migration `0003` seeds 7 demo products.

---

## 1. Run locally with Docker Compose

```bash
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | StockPilot UI |
| http://localhost:8000/api/docs | Swagger |
| http://localhost:8000/health · /ready · /metrics | Health and metrics |

Look at the database directly:

```bash
docker compose exec postgres psql -U stockpilot -c 'SELECT sku, name, quantity, reorder_level FROM products;'
```

Stop the stack with `docker compose down`. To also wipe the database volume, use `docker compose down -v`.

### Run without Docker (development)

```bash
# backend (needs a local PostgreSQL, or use: docker compose up postgres)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# frontend (proxies /api to :8000)
cd frontend && npm install && npm run dev     # http://localhost:5173
```

## 2. Tests

```bash
cd backend && pytest -v
```

The suite has 15 tests covering health and readiness, metrics, create/validate/duplicate-SKU, list with search and filters, get/404, partial update, delete, stock adjustment and its audit trail, the negative-stock guard, stats aggregation and cascade delete. `tests/conftest.py` swaps the database dependency for an **in-memory SQLite** database, so tests never touch PostgreSQL.

## 3. CI/CD (`.github/workflows/ci-cd.yml`)

The workflow runs on every push and pull request to `main`:

1. **test**: `pip install` and `pytest -v`, then `npm ci` and `npm run build`. A failing test stops the pipeline, so no image gets built.
2. **build-scan-push** (a matrix over backend and frontend): `docker build` tagged with `${{ github.sha }}`, then a **Trivy** scan with `severity: HIGH,CRITICAL` and `exit-code: 1`, then a push to `ghcr.io/<owner>/stockpilot-<component>:<sha>`. Pull requests build and scan the images but don't push them.
3. **deploy**: `helm upgrade --install` with the new SHA tags. This job runs only after you add the `KUBE_CONFIG_DATA` secret (see section 5). Until then it skips itself and stays green.

Each image tag is a commit SHA, never `latest`, so every running pod can be traced back to the exact commit that produced it.

> The Trivy action is pinned to a full commit SHA rather than a tag. Release tags can be moved by an attacker, and this happened to `trivy-action` itself in March 2026.

### What Trivy scans (M6 write-up)

Trivy unpacks each built image and checks two things against public CVE databases:
- the OS packages in the base image (Debian for `python:3.12-slim`, Alpine for `nginx-unprivileged`)
- the application libraries (Python wheels from `requirements.txt`, and the npm packages that end up in the image)

The pipeline only fails on **HIGH or CRITICAL** CVEs that have a fix available (`ignore-unfixed: true`). A green scan means no known, fixable, serious vulnerability was found when the image was built. It does not prove the image is secure. Trivy is one layer, alongside dependency pinning, non-root containers, secret hygiene and runtime controls.

## 4. AWS infrastructure (Terraform)

> **Doing this on a new AWS account's free credits?** Follow [`docs/aws-free-run.md`](docs/aws-free-run.md). `scripts/aws-session.sh` wraps the whole session (up → screenshots → down → leftover check).

Requirements: the AWS CLI configured (`aws configure` or SSO), Terraform 1.7 or later, kubectl and Helm.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars      # optional; defaults work
terraform init
terraform plan -out tfplan
terraform apply tfplan                             # ~15-20 min
$(terraform output -raw configure_kubectl)         # aws eks update-kubeconfig ...
kubectl get nodes
```

This creates:
- a VPC in `ap-south-1` across 2 AZs, with 2 public subnets (for load balancers), 2 private subnets (for nodes) and 1 NAT gateway
- an EKS cluster with a managed node group of 2× `t3.medium` (AL2023)
- the add-ons `vpc-cni`, `coredns`, `kube-proxy`, `eks-pod-identity-agent`, `aws-ebs-csi-driver` (IAM through Pod Identity, no static keys) and `metrics-server` (needed by the HPA)

> **Cost:** EKS control plane plus 2× t3.medium, the NAT gateway and the NLB come to roughly **US$5-6 per day**. Run `terraform destroy` when you're done (section 8).

No credentials are stored in this repo. `*.tfvars`, state files and `.terraform/` are git-ignored, and only `terraform.tfvars.example` is committed.

## 5. Deploy to Kubernetes with Helm

```bash
# Cluster bootstrap (once)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/storageclass-gp3.yaml

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Monitoring first, so the ServiceMonitor CRD exists before the app chart uses it
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/kube-prometheus-stack-values.yaml
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace -f k8s/ingress-nginx-values.yaml

# The app (CI does this automatically on each push once KUBE_CONFIG_DATA is set)
helm upgrade --install stockpilot ./helm/stockpilot -n stockpilot \
  -f helm/stockpilot/values-prod.yaml \
  --set backend.image.repository=ghcr.io/<your-gh-user>/stockpilot-backend \
  --set frontend.image.repository=ghcr.io/<your-gh-user>/stockpilot-frontend \
  --set backend.image.tag=<commit-sha> --set frontend.image.tag=<commit-sha>
```

**GHCR visibility:** GHCR packages start out private. Either make both packages public (on GitHub, open the package, then *Package settings → Change visibility*), or create a pull secret and pass `--set imagePullSecrets[0].name=ghcr-pull`.

**Enable automatic deploys from CI:**

```bash
# The EKS kubeconfig calls `aws eks get-token`, so the runner also needs AWS credentials
# for an IAM identity that has access to the cluster (for a class demo: the one that ran terraform apply).
base64 -w0 ~/.kube/config | gh secret set KUBE_CONFIG_DATA
gh secret set AWS_ACCESS_KEY_ID
gh secret set AWS_SECRET_ACCESS_KEY
```

**Open the app:**

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'   # browse to http://<that-hostname>/
```

The Ingress sends `/api` to the backend Service and `/` to the frontend Service.

### What the chart creates

| Resource | Notes |
|---|---|
| `stockpilot-backend` Deployment | 2-6 replicas managed by the HPA (60% CPU). Startup, liveness (`/health`) and readiness (`/ready`) probes. Runs as non-root with all capabilities dropped. |
| `stockpilot-frontend` Deployment | 2 replicas of nginx-unprivileged on :8080 |
| `stockpilot-postgres` StatefulSet | 1 replica with a 10 Gi encrypted gp3 PVC |
| Services | All ClusterIP: backend :8000, frontend :80, postgres :5432 |
| `stockpilot-db` Secret | Randomly generated DB password, kept across upgrades |
| Ingress, HPA, 2× PDB | |
| ServiceMonitor + Grafana dashboard ConfigMap | Scrapes `/metrics` every 15 s |

Useful commands: `helm list -n stockpilot`, `helm history stockpilot -n stockpilot`, `helm rollback stockpilot <rev> -n stockpilot`.

## 6. Autoscaling demo (HPA)

```bash
kubectl get hpa -n stockpilot -w                       # terminal 1
URL=http://<lb-hostname> ./scripts/load-test.sh 180 30 # terminal 2
kubectl top pods -n stockpilot                         # watch CPU rise and replicas go 2 → 3 → 4 …
```

## 7. Monitoring

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090   # http://localhost:9090/targets
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3001:80   # http://localhost:3001
kubectl get secret -n monitoring kube-prometheus-stack-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo                       # user: admin
```

In Prometheus, open **Status → Targets** and check that `serviceMonitor/stockpilot/stockpilot-backend` is **UP**.

In Grafana, open **Dashboards → StockPilot - Service Overview**. Its panels show:
- requests per second, p95 latency, 5xx error ratio and the number of backend pods up
- request rate by endpoint
- p50, p95 and p99 latency
- responses by status class
- backend CPU per pod (what the HPA sees)
- business metrics: stock adjustments by reason and units moved in and out

Run `./scripts/seed-activity.sh` to populate the business panels.

## 8. Tear down (avoid AWS charges)

```bash
helm uninstall stockpilot -n stockpilot
helm uninstall ingress-nginx -n ingress-nginx      # deletes the NLB; terraform destroy can hang if you skip this
helm uninstall kube-prometheus-stack -n monitoring
kubectl delete pvc --all -n stockpilot             # releases the EBS volume
cd terraform && terraform destroy
```

## 9. Troubleshooting lab

[`troubleshooting/`](troubleshooting/README.md) has five broken manifests: ImagePullBackOff, a Service with no endpoints, CrashLoopBackOff from a bad database URL, a readiness probe that fails, and a Pod stuck Pending on resources. Each comes with diagnosis steps and the fix.

## 10. Live demo script

1. Open the UI, create a product, adjust its stock, and watch the KPIs and movement feed update.
2. In `/api/docs`, run CRUD calls against `/api/products`. Show the `products` table in `psql`.
3. Make a visible change, e.g. change the `<h1>` in `frontend/src/App.jsx`, then `git commit` and `git push`.
4. In GitHub Actions, show the run: tests, then build, then the Trivy output, then the push, then the deploy.
5. In GHCR, show the new `:<sha>` tags.
6. Run `kubectl get pods -n stockpilot -w` to watch the rolling update, then refresh the browser to see the change.
7. Show `helm list` and `helm history`, then `kubectl get hpa` while `load-test.sh` is running.
8. Show the Prometheus targets and the Grafana dashboard.
9. Break something from `troubleshooting/`, then diagnose and fix it live.

## Grading rubric map

| Module | Where |
|---|---|
| M1 App | `backend/app/`, `backend/alembic/versions/`, `frontend/src/`, `docker-compose.yml` |
| M2 Tests | `backend/tests/` (15 tests), `backend/pytest.ini`, `tests/conftest.py` (SQLite test DB) |
| M3 Git | `.gitignore` covers `.env`, `__pycache__`, `node_modules`, `.venv`, tfstate |
| M4 Docker | `backend/Dockerfile` (uid 10001), `frontend/Dockerfile` (multi-stage, uid 101) |
| M5 CI/CD | `.github/workflows/ci-cd.yml` |
| M6 Trivy | The `Trivy scan` step plus the write-up in section 3 |
| M7 Terraform | `terraform/`, `terraform.tfvars.example` |
| M8 K8s + Helm | `k8s/`, `helm/stockpilot/` |
| M9 Observability | `/metrics`, `templates/servicemonitor.yaml`, `dashboards/stockpilot.json`, `monitoring/` |
| M10 Docs | This README, plus the demo script above |
