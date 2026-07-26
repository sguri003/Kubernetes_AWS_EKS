# GDS Solutions — AWS EKS Deployment

Django stock/commodity dashboard, containerized and deployed to an EKS cluster.

## Folder Structure

```
Kubernetes_AWS_EKS/
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── manage.py
├── stocks.py             # price data layer (yfinance + sqlite cache) — see module docstring
├── db.sqlite3            # baked into the image (not in .dockerignore) so pods start with data
├── deployment.yaml        # ACTIVE — Deployment manifest
├── services.yaml          # ACTIVE — Service (LoadBalancer/NLB) manifest
├── cluster-config.yaml    # ACTIVE — eksctl cluster config
├── web_app/               # Django project settings, urls, wsgi
├── main/                  # Django app (views, urls, templates via templates/main/)
├── templates/              # HTML templates
└── k8s/                   # NOT USED — old ECR/Ingress-based template, kept for reference only
    ├── secret.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

**Only the root-level manifests (`deployment.yaml`, `services.yaml`, `cluster-config.yaml`) are
live.** The `k8s/` folder is an older, unused template (ECR image + Ingress instead of Docker Hub
+ LoadBalancer) — don't apply it and don't treat it as the source of truth.

## Prerequisites

- Docker installed locally
- AWS CLI configured, `kubectl` pointed at the right context (see gotcha below)
- EKS cluster `gds-yaml-cluster` (region `us-east-1`) already created, with the AWS Load
  Balancer Controller installed in `kube-system`
- Docker Hub access to push `sguri003/gds-app` (public repo, no ECR involved)

## Deploy Steps

### 1. Build & push the image, tagging with a new version

Always bump the tag (`v12` → `v13`, etc.) instead of reusing one — reusing a tag makes
`kubectl apply` unreliable about detecting the change and rolling out. `APP_VERSION` must be
passed as a build-arg matching the image tag; it's what shows in the dashboard header
("Current Release: sguri003/gds-app:vNN"), and it is **not** inferred automatically.

```bash
docker build --build-arg APP_VERSION=v13 -t sguri003/gds-app:v13 .
docker push sguri003/gds-app:v13
```

### 2. Point the Deployment at the new tag

Edit `deployment.yaml` line 19 (`image: sguri003/gds-app:vNN`) to the new tag.

### 3. Apply and roll out

```bash
kubectl apply -f deployment.yaml
kubectl apply -f services.yaml
kubectl rollout status deployment/gds-deployment
```

### 4. Get the Load Balancer URL

```bash
kubectl get service gds-service
```

The `EXTERNAL-IP` column shows the NLB hostname — open it in a browser.

## Gotcha: check your kubectl context first

`kubectl` can silently be pointed at `docker-desktop` (Docker Desktop's local Kubernetes)
instead of the real `gds-yaml-cluster` EKS cluster — the giveaway is a `local-path-storage`
namespace. Every "my deploy isn't showing up" / "the Service keeps disappearing" symptom has
turned out to be this. Before troubleshooting any deploy issue:

```bash
kubectl config current-context
# if wrong:
aws eks update-kubeconfig --name gds-yaml-cluster --region us-east-1
```

## Data / cold-start behavior

- `db.sqlite3` is baked into the image (`COPY . .` in the Dockerfile), so every pod starts
  with real historical price data instead of an empty DB.
- Each pod has its own ephemeral filesystem — no shared storage between the 2 replicas. On
  startup each pod independently runs a cheap incremental refresh (`stocks.refresh_all_to_sql()`,
  ~5-day trailing window, not a full re-download) to catch up on anything since the image was
  built. Fine at 2 replicas; revisit if replica count grows significantly.
- `stocks.refresh_if_stale()` refreshes at most once per day, after 5PM ET (post market close).

## Environment Variables

| Variable          | Default              | Description                              |
|--------------------|----------------------|-------------------------------------------|
| DJANGO_SECRET_KEY  | change-me-in-production | Django secret key (required in prod)   |
| DJANGO_DEBUG       | False                | Enable debug mode                         |
| ALLOWED_HOSTS      | *                    | Comma-separated allowed hosts             |
| APP_VERSION        | dev                  | Set via Docker build-arg; shown in the dashboard header |

## Browser DNS quirk

If the NLB hostname loads fine via `curl`/`Invoke-WebRequest` but times out in the browser
specifically, check the browser's "Secure DNS" (DNS-over-HTTPS) setting — toggling it off (or
to "current provider") has fixed this before. Freshly-created ELB hostnames can resolve
inconsistently through DoH providers even when the OS resolver works fine.
