# Submission screenshots

Save the screenshots the grading rubric asks for in this folder:

| File | Module | How to get it |
|---|---|---|
| `01-app-browser.png` | M1/M4 | `docker compose up --build`, open http://localhost:3000 |
| `02-compose-up.png` | M4 | Terminal running `docker compose up --build` |
| `03-pytest.png` | M2 | `cd backend && pytest -v` |
| `04-git-log.png` | M3 | `git log --oneline` (10+ commits) |
| `05-actions-green.png` | M5 | GitHub → Actions → a successful run |
| `06-trivy.png` | M6 | The "Trivy scan" step log in that run |
| `07-ghcr.png` | M5 | GitHub → Packages → stockpilot-backend / -frontend with SHA tags |
| `08-terraform-plan.png` | M7 | `terraform plan` |
| `09-aws-vpc-eks.png` | M7 | AWS Console → VPC and EKS in ap-south-1 |
| `10-kubectl-pods-svc.png` | M8 | `kubectl get pods,svc -n stockpilot` |
| `11-helm-list.png` | M8 | `helm list -n stockpilot` |
| `12-ingress-browser.png` | M8 | App opened via the load balancer hostname |
| `13-hpa.png` | M8 | `kubectl get hpa -n stockpilot` during `scripts/load-test.sh` |
| `14-metrics-curl.png` | M9 | `curl http://localhost:8000/metrics` |
| `15-prometheus-targets.png` | M9 | Prometheus → Status → Targets (stockpilot-backend UP) |
| `16-grafana.png` | M9 | Grafana → StockPilot - Service Overview |
| `17-terraform-destroy.png` | M7 | `terraform destroy` completed |
