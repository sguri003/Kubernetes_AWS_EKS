# Stocks App — AWS EKS Deployment

Django stock dashboard, containerized for AWS EKS.

## Folder Structure

```
Kubernetes_AWS_EKS/
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── manage.py
├── stocks.py
├── stock_data.csv
├── web_app/          # Django project settings, urls, wsgi
├── main/             # Django app (views, urls)
├── templates/        # HTML templates
└── k8s/
    ├── secret.yaml   # Django secret key (edit before applying)
    ├── deployment.yaml
    ├── service.yaml
    └── ingress.yaml
```

## Prerequisites

- Docker installed locally
- AWS CLI configured
- An EKS cluster with the **AWS Load Balancer Controller** installed
- An ECR repository created for the image

## Deploy Steps

### 1. Edit the Secret

Open `k8s/secret.yaml` and replace the placeholder with a real secret key:

```yaml
stringData:
  secret-key: "your-strong-random-secret-here"
```

### 2. Build & Push Docker Image

```bash
# Set your ECR URI
ECR_URI=<your-account-id>.dkr.ecr.<region>.amazonaws.com/stocks-app

# Build
docker build -t stocks-app .

# Tag
docker tag stocks-app:latest $ECR_URI:latest

# Login to ECR (run this yourself — requires AWS credentials)
# aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin $ECR_URI

# Push
docker push $ECR_URI:latest
```

### 3. Update Image in Deployment

Edit `k8s/deployment.yaml` and replace `<YOUR_ECR_URI>` with your actual ECR URI.

### 4. Apply Kubernetes Manifests

```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

### 5. Get the Load Balancer URL

```bash
kubectl get ingress stocks-ingress
```

The ADDRESS column shows the ALB DNS name — open it in a browser.

## Environment Variables

| Variable          | Default              | Description                  |
|-------------------|----------------------|------------------------------|
| DJANGO_SECRET_KEY | change-me-in-production | Django secret key (required) |
| DJANGO_DEBUG      | False                | Enable debug mode            |
| ALLOWED_HOSTS     | *                    | Comma-separated allowed hosts |
