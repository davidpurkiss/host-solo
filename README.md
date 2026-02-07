# Host Solo

A lightweight self-hosted application platform for VPS deployments.

Host Solo simplifies deploying and managing containerized applications on a single VPS with:

- **Multi-environment support** - Run dev, staging, and prod on the same server with network isolation
- **Automatic SSL** - Let's Encrypt certificates via Traefik reverse proxy
- **DNS management** - Automatic DNS record creation (DNSimple, extensible to other providers)
- **Cloud backups** - S3-compatible backup to AWS S3, Backblaze B2, MinIO, etc.

## Installation

```bash
pip install hostsolo
```

Or install from source:

```bash
git clone https://github.com/yourusername/host-solo.git
cd host-solo
pip install -e .
```

## Quick Start

### 1. Initialize a project

```bash
hostsolo init
```

This creates:
- `hostsolo.yaml` - Main configuration file
- `.env.example` - Template for CLI credentials (DNS, backup)
- `config/<app>/` - Per-app configuration directories
- `data/` - Directory for persistent data
- `.gitignore` - Excludes sensitive files

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in DNS/backup credentials:

```bash
cp .env.example .env
```

### 3. Set up app environment files

For each app, create environment-specific config files:

```bash
# Shared config (same for all environments)
cp config/directus/env.example config/directus/shared.env

# Environment-specific config (overrides shared)
cp config/directus/env.example config/directus/dev.env
cp config/directus/env.example config/directus/prod.env
```

Edit each file with appropriate values:
- `shared.env` - Non-sensitive values shared across all environments
- `dev.env` - Development secrets and settings
- `prod.env` - Production secrets and settings

### 4. Start the reverse proxy

```bash
hostsolo proxy up
```

### 5. Deploy an application

```bash
hostsolo deploy up directus --env prod
```

## CLI Commands

### Proxy Management

```bash
hostsolo proxy up       # Start Traefik reverse proxy
hostsolo proxy down     # Stop Traefik
hostsolo proxy logs     # View Traefik logs
hostsolo proxy restart  # Restart Traefik
```

### Application Deployment

```bash
hostsolo deploy up <app> --env <env>           # Deploy an app
hostsolo deploy up <app> --env <env> --tag 1.0 # Deploy specific version
hostsolo deploy stop <app> --env <env>         # Stop an app
hostsolo deploy logs <app> --env <env>         # View app logs
hostsolo deploy restart <app> --env <env>      # Restart an app
```

### DNS Management

```bash
hostsolo dns setup --env <env>  # Create/update DNS record
hostsolo dns list               # List all DNS records
hostsolo dns delete --env <env> # Delete DNS record
```

### Backup Management

```bash
hostsolo backup now <app> --env <env>                        # Create backup
hostsolo backup list <app> --env <env>                       # List backups
hostsolo backup restore <app> --env <env> --timestamp <ts>   # Restore backup
hostsolo backup delete <app> --env <env> --timestamp <ts>    # Delete backup
```

### Environment Management

```bash
hostsolo env list                          # List environments
hostsolo env create <name>                 # Create environment
hostsolo env destroy <name>                # Destroy environment
hostsolo env destroy <name> --remove-data  # Destroy with data
```

### Status

```bash
hostsolo status  # Show status of all deployments
```

## Configuration

### hostsolo.yaml

```yaml
domain: example.com
email: admin@example.com

dns:
  provider: dnsimple

backup:
  provider: s3
  bucket: my-backups
  schedule: "0 */6 * * *"

environments:
  dev:
    subdomain: dev
  staging:
    subdomain: staging
  prod:
    subdomain: ""  # Root domain

apps:
  directus:
    image: directus/directus
    tag: "10.10.5"
    ports:
      - "8055"
    volumes:
      - ./data/${ENV}/directus/database:/directus/database
    environment:
      DB_CLIENT: sqlite3
      DB_FILENAME: /directus/database/data.db
    backup_paths:
      - ./data/${ENV}/directus/database
```

### Environment Variables

The root `.env` file contains CLI credentials:

```bash
# DNS (DNSimple)
HOSTSOLO_DNSIMPLE_TOKEN=your-token
HOSTSOLO_DNSIMPLE_ACCOUNT_ID=your-account-id

# Backup (S3-compatible)
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

### App Configuration (Layered .env files)

Each app has its own configuration directory with layered environment files:

```
config/
├── directus/
│   ├── env.example      # Template
│   ├── shared.env       # Shared across all environments
│   ├── dev.env          # Development overrides
│   ├── staging.env      # Staging overrides
│   └── prod.env         # Production overrides
└── another-app/
    └── ...
```

**Variable precedence** (later overrides earlier):
1. `shared.env` - Base values for all environments
2. `{env}.env` - Environment-specific overrides
3. `environment:` in hostsolo.yaml - Static defaults

Example `config/directus/shared.env`:
```bash
DB_CLIENT=sqlite3
DB_FILENAME=/directus/database/data.db
TZ=UTC
```

Example `config/directus/prod.env`:
```bash
KEY=production-secret-key
SECRET=production-secret
ADMIN_PASSWORD=super-secure-password
```

Example `config/directus/dev.env`:
```bash
KEY=dev-key
SECRET=dev-secret
ADMIN_PASSWORD=admin
```

## Local Development

Use the `--local` flag to run locally without SSL:

```bash
hostsolo proxy up --local
hostsolo deploy up directus --env dev --local
```

Access via http://dev.localhost (add to /etc/hosts if needed).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                     VPS                          │
│  ┌─────────────────────────────────────────┐    │
│  │              Traefik                     │    │
│  │      (Reverse Proxy + SSL)              │    │
│  │           :80, :443                      │    │
│  └─────────────────────────────────────────┘    │
│           │           │           │             │
│     ┌─────▼─────┐ ┌───▼───┐ ┌────▼────┐        │
│     │   dev     │ │staging│ │  prod   │        │
│     │  network  │ │network│ │ network │        │
│     └─────┬─────┘ └───┬───┘ └────┬────┘        │
│           │           │          │              │
│     ┌─────▼─────┐ ┌───▼───┐ ┌────▼────┐        │
│     │   App     │ │  App  │ │   App   │        │
│     │ (SQLite)  │ │(SQLite)│ │(SQLite) │        │
│     └───────────┘ └───────┘ └─────────┘        │
└─────────────────────────────────────────────────┘
```

## License

MIT
