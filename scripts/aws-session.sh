#!/usr/bin/env bash
# One short, cheap AWS session for the capstone: create -> screenshot -> destroy.
#
#   ./scripts/aws-session.sh preflight   # tools + which AWS account/region you are about to use
#   ./scripts/aws-session.sh up          # terraform plan + apply (VPC + EKS), configure kubectl
#   ./scripts/aws-session.sh deploy      # ingress-nginx, Prometheus/Grafana, StockPilot via Helm
#   ./scripts/aws-session.sh urls        # app URL + port-forward commands for Prometheus/Grafana
#   ./scripts/aws-session.sh down        # uninstall everything, terraform destroy, check for leftovers
#   ./scripts/aws-session.sh leftovers   # list anything still costing money in the region
#
# deploy needs: GH_OWNER=<github user>  IMAGE_TAG=<commit sha pushed by CI>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT/terraform"
REGION="${AWS_REGION:-ap-south-1}"
NS=stockpilot
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is not installed (see docs/aws-free-run.md, step 2)"; }

confirm() {
  read -r -p "$1 [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || die "Aborted."
}

cluster_name() { terraform -chdir="$TF_DIR" output -raw cluster_name 2>/dev/null || true; }

preflight() {
  say "Checking tools"
  for t in aws terraform; do need "$t"; printf '  %-10s %s\n' "$t" "$($t --version 2>/dev/null | head -1 || true)"; done
  for t in kubectl helm; do   # only needed for the optional 'deploy' step
    command -v "$t" >/dev/null 2>&1 && printf '  %-10s installed\n' "$t" || printf '  %-10s not installed (only needed for deploy)\n' "$t"
  done
  say "Checking AWS credentials"
  aws sts get-caller-identity --output table || die "AWS credentials not configured (run: aws configure)"
  echo "Region: $REGION"
}

up() {
  preflight
  say "terraform init / plan"
  terraform -chdir="$TF_DIR" init -input=false
  terraform -chdir="$TF_DIR" plan -input=false -out=tfplan
  warn "Screenshot the plan summary above for M7 ('Plan: N to add')."
  confirm "Create these resources now? (~15-20 minutes; billed by the hour until 'down')"
  terraform -chdir="$TF_DIR" apply -input=false tfplan
  rm -f "$TF_DIR/tfplan"
  say "Configuring kubectl"
  aws eks update-kubeconfig --region "$REGION" --name "$(cluster_name)"
  aws eks describe-cluster --name "$(cluster_name)" --query 'cluster.{name:name,version:version,status:status}' --output table
  aws eks list-nodegroups --cluster-name "$(cluster_name)" --output table
  command -v kubectl >/dev/null 2>&1 && kubectl get nodes -o wide
  warn "Screenshot now: AWS Console -> VPC (Your VPCs, Subnets) and EKS -> Clusters (region ap-south-1)."
}

deploy() {
  need kubectl; need helm
  : "${GH_OWNER:?set GH_OWNER=<your github username>}"
  : "${IMAGE_TAG:?set IMAGE_TAG=<full commit sha that CI pushed to GHCR>}"
  local owner; owner="$(echo "$GH_OWNER" | tr '[:upper:]' '[:lower:]')"

  say "Cluster bootstrap"
  kubectl apply -f "$ROOT/k8s/namespace.yaml" -f "$ROOT/k8s/storageclass-gp3.yaml"
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo update >/dev/null

  say "Installing kube-prometheus-stack (Prometheus + Grafana)"
  helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    -n monitoring --create-namespace -f "$ROOT/monitoring/kube-prometheus-stack-values.yaml" --wait --timeout 15m

  say "Installing ingress-nginx (creates an AWS Network Load Balancer)"
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    -n ingress-nginx --create-namespace -f "$ROOT/k8s/ingress-nginx-values.yaml" --wait --timeout 10m

  say "Deploying StockPilot ${IMAGE_TAG:0:7}"
  helm upgrade --install stockpilot "$ROOT/helm/stockpilot" -n "$NS" \
    -f "$ROOT/helm/stockpilot/values-prod.yaml" \
    --set backend.image.repository="ghcr.io/$owner/stockpilot-backend" \
    --set frontend.image.repository="ghcr.io/$owner/stockpilot-frontend" \
    --set backend.image.tag="$IMAGE_TAG" --set frontend.image.tag="$IMAGE_TAG" \
    --wait --timeout 10m
  kubectl get pods,svc,ingress,hpa -n "$NS"
  helm list -n "$NS"
  urls
}

urls() {
  local lb
  lb="$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  say "Endpoints"
  echo "App (may take ~3 min for DNS):  http://${lb:-<pending>}/"
  echo "Prometheus:  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090   -> http://localhost:9090/targets"
  echo "Grafana:     kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3001:80   -> http://localhost:3001  (user admin)"
  echo "Grafana pw:  kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d; echo"
  echo "HPA demo:    URL=http://${lb:-<lb>} ./scripts/load-test.sh 180 30   (watch: kubectl get hpa -n $NS -w)"
}

down() {
  preflight
  confirm "Destroy ALL capstone resources in $REGION?"
  if command -v kubectl >/dev/null 2>&1 && command -v helm >/dev/null 2>&1 && kubectl cluster-info >/dev/null 2>&1; then
    say "Removing Kubernetes-created AWS resources first (load balancer, EBS volumes)"
    helm uninstall stockpilot -n "$NS" --wait 2>/dev/null || true
    kubectl delete pvc --all -n "$NS" --wait=true 2>/dev/null || true
    helm uninstall ingress-nginx -n ingress-nginx --wait 2>/dev/null || true
    helm uninstall kube-prometheus-stack -n monitoring --wait 2>/dev/null || true
    say "Waiting 60s for AWS to delete the load balancer"
    sleep 60
  else
    warn "kubectl cannot reach the cluster; skipping in-cluster cleanup."
  fi
  say "terraform destroy"
  terraform -chdir="$TF_DIR" destroy -input=false -auto-approve
  warn "Screenshot the 'Destroy complete!' line above for M7."
  leftovers
}

leftovers() {
  say "Checking $REGION for anything that still costs money"
  local found=0 out
  out="$(aws eks list-clusters --query 'clusters' --output text)";                                   [[ -n "$out" ]] && { warn "EKS clusters: $out"; found=1; }
  out="$(aws ec2 describe-nat-gateways --filter Name=state,Values=available,pending --query 'NatGateways[].NatGatewayId' --output text)"; [[ -n "$out" ]] && { warn "NAT gateways: $out"; found=1; }
  out="$(aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerName' --output text)"; [[ -n "$out" ]] && { warn "Load balancers: $out"; found=1; }
  out="$(aws elb describe-load-balancers --query 'LoadBalancerDescriptions[].LoadBalancerName' --output text)"; [[ -n "$out" ]] && { warn "Classic load balancers: $out"; found=1; }
  out="$(aws ec2 describe-instances --filters Name=instance-state-name,Values=pending,running --query 'Reservations[].Instances[].InstanceId' --output text)"; [[ -n "$out" ]] && { warn "EC2 instances: $out"; found=1; }
  out="$(aws ec2 describe-volumes --filters Name=status,Values=available,in-use --query 'Volumes[].VolumeId' --output text)"; [[ -n "$out" ]] && { warn "EBS volumes: $out"; found=1; }
  out="$(aws ec2 describe-addresses --query 'Addresses[].AllocationId' --output text)";             [[ -n "$out" ]] && { warn "Elastic IPs: $out"; found=1; }
  if [[ $found -eq 0 ]]; then
    printf '\033[1;32mOK  Nothing billable left in %s.\033[0m\n' "$REGION"
  else
    warn "Delete the resources above in the AWS Console (region $REGION), then re-run: $0 leftovers"
  fi
}

case "${1:-}" in
  preflight|up|deploy|urls|down|leftovers) "$1" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
