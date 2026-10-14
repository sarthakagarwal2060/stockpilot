# Running the AWS part for free

The goal is to earn the M7 Terraform points (VPC + EKS provisioned, then destroyed) using only the credits AWS gives new accounts. You never pay anything.

**What actually has to run on AWS:** only the infrastructure, meaning the VPC and an EKS cluster with worker nodes. An empty cluster is enough for M7. Deploying the frontend and backend onto EKS is **optional** (step 5). Helm, Ingress, HPA and Grafana can all be shown on a free local cluster instead.

> **Free-plan limits:** only Free Tier–eligible instance types can launch (`t3.micro/small`, `c7i-flex.large`, `m7i-flex.large`, …), so worker nodes use `c7i-flex.large`.
>
> **Free-plan region lock:** Free-plan accounts can only use their **home region**, which is the region the console first opens in. Every other region returns `explicit deny in a service control policy`. This project defaults to `ap-southeast-2` (Sydney) for that reason. If your account's home region is different, set `aws_region` in `terraform/terraform.tfvars` and run `export AWS_REGION=<region>` before using the script. Spot instances are also blocked on the Free plan, so keep `node_capacity_type = "ON_DEMAND"`.

## Cost, in credits

| Resource | Approx. price in ap-southeast-2 |
|---|---|
| EKS control plane | $0.10 / hour |
| 2× c7i-flex.large worker nodes | ~$0.11 / hour |
| NAT gateway | ~$0.06 / hour |
| Network Load Balancer (only if you deploy, step 5) | ~$0.02 / hour |
| **Total** | **~$0.30 / hour** |

A full session takes about 1-2 hours, so it costs **under $1 out of the $100 sign-up credit**. On the **Free plan** AWS cannot charge your card at all. If the credits ever ran out, the account would be paused, not billed.

---

## Step 1: Create the AWS account (about 10 min)

1. Sign up at https://aws.amazon.com/free and **choose "Free plan"** when asked. Do *not* pick "Paid plan".
   - You only get the credits on a brand-new account. An old account would bill your card.
   - AWS still asks for a card to verify your identity. On the Free plan it isn't charged.
2. Sign in as the root user and turn on **MFA** (top-right menu → *Security credentials*).
3. **Earn extra credits (optional):** the *Explore AWS* widget on the console home page pays $20 per task. One task is creating a budget (*Billing → Budgets → Create budget → "Zero spend budget"*), which also emails you if anything ever costs money.
4. Create a user for the command line:
   1. Go to *IAM → Users → Create user* and name it `capstone-admin`.
   2. Choose *Attach policies directly* and select `AdministratorAccess`. Create the user.
   3. Open the user, go to *Security credentials → Create access key*, and choose *Command Line Interface (CLI)*. Copy both keys.
   - **Never commit these keys** or paste them into any file in this repo.

## Step 2: Install the tools (about 5 min, Linux)

```bash
# AWS CLI v2
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install

# Terraform (HashiCorp apt repo)
wget -qO- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform

# Only needed for the optional deploy in step 5:
sudo snap install kubectl --classic
sudo snap install helm --classic
```

Then configure your credentials:

```bash
aws configure          # paste the two keys; region: ap-southeast-2; output: json
```

## Step 3: Create the infrastructure (about 20 min)

```bash
cd Capstone
./scripts/aws-session.sh preflight   # shows which account you're about to use
./scripts/aws-session.sh up          # plan → asks for confirmation → apply
```

Take these screenshots:

| When | Screenshot | Module |
|---|---|---|
| After `plan` | The plan output ending in `Plan: NN to add, 0 to change, 0 to destroy` | M7 |
| After `apply` | The `Apply complete!` line and the outputs | M7 |
| AWS Console, region **Asia Pacific (Sydney) ap-southeast-2** | *VPC → Your VPCs* (`stockpilot-dev-vpc`) and *Subnets* (2 public + 2 private) | M7 |
| AWS Console | *EKS → Clusters → stockpilot-dev-eks*, plus the *Compute* tab showing the node group | M7 |

**If `apply` fails with an access or "not allowed on free plan" error:** Free-plan accounts block some services. The VPC is usually already created by that point, so screenshot it anyway. Then run `./scripts/aws-session.sh down` and tell your instructor that EKS is blocked on the free plan; you can still show `plan` and the code. Don't upgrade to the Paid plan unless you're fine with possible card charges.

## Step 4: Destroy everything (about 15 min). Don't skip this.

```bash
./scripts/aws-session.sh down
```

- Screenshot the `Destroy complete!` line (M7).
- The script then checks the region for leftovers (EKS clusters, NAT gateways, load balancers, instances, EBS volumes, Elastic IPs). You want to see **`OK  Nothing billable left in ap-southeast-2.`**
- You can re-check at any time with `./scripts/aws-session.sh leftovers`.

---

## Step 5 (optional): Deploy the app on EKS before step 4

Do this only if you want the Ingress, HPA and Grafana screenshots from AWS rather than a local cluster. It adds about 20 minutes, or roughly $0.10 of credits.

Prerequisites:
- The repo is pushed to GitHub and the CI run is green, so both images exist in GHCR.
- Both GHCR packages are **public**: *GitHub → your profile → Packages → stockpilot-backend → Package settings → Change visibility*. Repeat for `stockpilot-frontend`.

```bash
GH_OWNER=<your-github-username> IMAGE_TAG=$(git rev-parse HEAD) ./scripts/aws-session.sh deploy
./scripts/aws-session.sh urls        # app URL, Prometheus/Grafana port-forward commands
```

Take the M8 and M9 screenshots listed in `docs/screenshots/README.md`, then go back to **step 4**. The `down` command removes the load balancer and volumes before it destroys the cluster.
