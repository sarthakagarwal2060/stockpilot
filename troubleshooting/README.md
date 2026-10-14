# Troubleshooting lab

Each manifest is deliberately broken. Apply it, diagnose it with `kubectl`, then fix it.

| # | File | Symptom | Root cause |
|---|------|---------|------------|
| 1 | `01-broken-image.yaml` | `ImagePullBackOff` | Image tag does not exist |
| 2 | `02-broken-service.yaml` | Service has no endpoints | Selector labels don't match any Pod |
| 3 | `03-crashloop-bad-db-url.yaml` | `CrashLoopBackOff` | Backend cannot reach the database (wrong host) |
| 4 | `04-not-ready-wrong-probe.yaml` | Pods `Running` but `0/1 READY` | Readiness probe points at a path that returns 404 |
| 5 | `05-pending-resources.yaml` | Pod stuck `Pending` | Requests more CPU than any node has |

General workflow:

```bash
kubectl get pods -n stockpilot
kubectl describe pod <pod> -n stockpilot          # Events section at the bottom
kubectl logs <pod> -n stockpilot --previous       # logs from the crashed container
kubectl get events -n stockpilot --sort-by=.lastTimestamp
kubectl get endpointslices -n stockpilot
kubectl get pods -n stockpilot --show-labels
```

Clean up: `kubectl delete -f troubleshooting/ -n stockpilot --ignore-not-found`

<details><summary>Fixes</summary>

1. Point `image:` at a tag that exists in GHCR (`kubectl set image deploy/broken-image app=nginxinc/nginx-unprivileged:1.31-alpine -n stockpilot`).
2. Change the Service selector to the backend Pod labels (`app.kubernetes.io/component: backend`, `app.kubernetes.io/instance: stockpilot`).
3. `kubectl logs --previous` shows `could not translate host name "postgres-wrong"`; use `stockpilot-postgres`.
4. `kubectl describe pod` shows `Readiness probe failed: HTTP probe failed with statuscode: 404`; change the path to `/ready`.
5. `kubectl describe pod` shows `0/2 nodes are available: 2 Insufficient cpu`; lower `resources.requests.cpu`.
</details>
