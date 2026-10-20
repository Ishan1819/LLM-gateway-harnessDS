"""Background worker processes, each run as its own Kubernetes Deployment.

    python -m app.workers.usage_worker   consume usage events -> Postgres
    python -m app.workers.alert_worker   elected leader scans caps -> alerts
"""
