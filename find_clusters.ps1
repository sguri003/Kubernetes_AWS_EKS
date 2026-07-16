$region = "us-east-1"

$clusters = aws eks list-clusters --region $region --query 'clusters[]' --output text
$clusters = $clusters -split "\s+"

foreach ($c in $clusters) {
    Write-Host "=== $c ===" -ForegroundColor Cyan
    aws eks update-kubeconfig --name $c --region $region | Out-Null
    kubectl get deployments -A
}
