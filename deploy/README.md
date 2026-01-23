# AEL Deployment

This directory contains all deployment manifests and configurations for AEL.

## Directory Structure

```
deploy/
├── docker/                    # Docker Compose configurations
│   ├── docker-compose.yml     # Production deployment
│   ├── docker-compose.dev.yaml    # Development with hot-reload
│   └── docker-compose.homelab.yaml # Full homelab stack
├── k8s/                       # Kubernetes manifests
│   ├── namespace.yaml         # AEL namespace
│   ├── secrets.yaml.example   # Secrets template (copy to secrets.yaml)
│   ├── configmap.yaml         # AEL configuration
│   ├── workflows-configmap.yaml # Workflow definitions
│   ├── zookeeper.yaml         # Zookeeper StatefulSet
│   ├── kafka.yaml             # Kafka StatefulSet
│   ├── native-tools.yaml      # Native tools Deployment
│   ├── ael.yaml               # AEL Deployment
│   └── ingress.yaml           # Traefik Ingress
└── README.md                  # This file
```

## Quick Start

All deployment commands are available via the root Makefile:

```bash
# Build and push Docker images
make deploy-images

# Deploy to Kubernetes
make deploy-k8s

# Full deployment (build, push, rollout)
make deploy

# Check status
make deploy-status
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `deploy-build` | Build Docker images for deployment |
| `deploy-push` | Push images to registry |
| `deploy-images` | Build and push images |
| `deploy-k8s` | Deploy AEL stack to Kubernetes |
| `deploy-rollout` | Restart deployments (pick up new images) |
| `deploy` | Full deployment (build, push, rollout) |
| `deploy-status` | Check deployment status |
| `deploy-logs` | View AEL logs |
| `deploy-local` | Start local stack with docker-compose |
| `deploy-local-down` | Stop local stack |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REGISTRY` | `192.168.68.203:5000` | Docker registry URL |
| `PLATFORM` | `linux/amd64` | Target platform for builds |
| `K8S_NAMESPACE` | `ael` | Kubernetes namespace |
| `KUBECONFIG` | `~/.kube/config` | Path to kubeconfig |

### Secrets

Before deploying to Kubernetes, create `deploy/k8s/secrets.yaml` from the example:

```bash
cp deploy/k8s/secrets.yaml.example deploy/k8s/secrets.yaml
# Edit secrets.yaml with your values
```

## Deployment Options

### 1. Kubernetes (K3s/K8s)

```bash
# First time deployment
make deploy-k8s

# Update deployment (after code changes)
make deploy
```

### 2. Docker Compose (Local)

```bash
# Start full stack
make deploy-local

# Stop stack
make deploy-local-down
```

### 3. Development

```bash
# Development with hot-reload
docker compose -f deploy/docker/docker-compose.dev.yaml up -d
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    ael namespace                         ││
│  │  ┌─────────┐  ┌──────────────┐  ┌─────────┐            ││
│  │  │   AEL   │──│ native-tools │  │  Kafka  │            ││
│  │  │  :8082  │  │    :8081     │  │  :9092  │            ││
│  │  └────┬────┘  └──────────────┘  └────┬────┘            ││
│  │       │                              │                  ││
│  │       │                         ┌────┴────┐            ││
│  │       │                         │Zookeeper│            ││
│  │       │                         │  :2181  │            ││
│  │       │                         └─────────┘            ││
│  └───────┼──────────────────────────────────────────────────┘│
│          │                                                   │
│  ┌───────┴───────┐                                          │
│  │    Ingress    │  ael.ostanlabs.homelab                   │
│  │   (Traefik)   │                                          │
│  └───────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

