data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "${var.project}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Networking: VPC with 2 public + 2 private subnets across 2 AZs, one NAT GW.
# Worker nodes live in private subnets; load balancers go in public subnets.
# ---------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.21.0"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 101)]
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 1)]

  enable_nat_gateway   = true
  single_nat_gateway   = true # one NAT keeps cost down for a demo
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Tags the AWS Load Balancer integration uses to discover subnets.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ---------------------------------------------------------------------------
# EKS cluster + one managed node group.
# ---------------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.37.2"

  cluster_name    = "${local.name}-eks"
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true

  node_security_group_additional_rules = {
    # The module only opens node-to-node ports 1025-65535. kube-proxy forwards load balancer
    # traffic to ingress-nginx pods on *other* nodes on port 80, so allow all traffic between nodes.
    ingress_self_all = {
      description = "Node to node, all ports"
      type        = "ingress"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      self        = true
    }
    # The EKS metrics-server add-on serves on 10251; the API server must reach it for `kubectl top` and the HPA.
    ingress_cluster_metrics_server = {
      description                   = "Cluster API to metrics-server"
      type                          = "ingress"
      protocol                      = "tcp"
      from_port                     = 10251
      to_port                       = 10251
      source_cluster_security_group = true
    }
  }

  # Pods get AWS permissions through EKS Pod Identity (see aws_iam_role.ebs_csi), so the
  # IRSA OIDC provider isn't needed - and AWS Free-plan accounts are not allowed to create one.
  enable_irsa = false

  cluster_addons = {
    coredns                = {}
    kube-proxy             = {}
    vpc-cni                = { before_compute = true }
    eks-pod-identity-agent = { before_compute = true }
    # PersistentVolumes for PostgreSQL (gp3 EBS volumes)
    aws-ebs-csi-driver = {
      pod_identity_association = [{
        role_arn        = aws_iam_role.ebs_csi.arn
        service_account = "ebs-csi-controller-sa"
      }]
    }
    # Resource metrics for `kubectl top` and the HorizontalPodAutoscaler
    metrics-server = {}
  }

  eks_managed_node_groups = {
    main = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type

      min_size     = var.node_min_size
      desired_size = var.node_desired_size
      max_size     = var.node_max_size

      labels = { workload = "general" }
    }
  }
}

# ---------------------------------------------------------------------------
# IAM role for the EBS CSI driver, granted to its service account via
# EKS Pod Identity (no static credentials anywhere).
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  name               = "${local.name}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}
