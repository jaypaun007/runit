# ⚡ Runit — Zero-Config Project Runner

**One command to clone, setup, and run any GitHub repo. No Docker. No TTY. No manual setup.**

```bash
pip install git+https://github.com/jaypaun007/runit.git
runit https://github.com/user/repo --yes
```

Works everywhere: **Kaggle**, **Colab**, **headless VPS**, **local machine**.

## How It Works

```
runit https://github.com/user/repo
  │
  ├─ [1/4] Analyze        → detect language, services, env vars (rule-based, 0 AI cost)
  ├─ [2/4] Services       → install PostgreSQL, Redis, MySQL, etc. (apt / Docker / binary)
  ├─ [3/4] Env Web UI     → tunneled HTML form to fill API keys in your browser
  └─ [4/4] Run            → smart pip install (unpin versions, detect imports),
                             start project, expose via cloudflared tunnel
```

### 1. Analyze (deterministic — zero AI cost)

Scans the repo for `requirements.txt`, `package.json`, `.env.example`, `Dockerfile`, `README.md`. Detects:
- **Language**: Python, Node.js, Go, Rust, and 15+ more
- **Services**: PostgreSQL, Redis, MySQL, MongoDB, RabbitMQ, MariaDB, Elasticsearch, ClickHouse, Neo4j
- **Env vars**: all keys from `.env.example`, matched to service credentials

### 2. Services (3-tier fallback)

| Service | Tier 1: Docker | Tier 2: apt | Tier 3: Binary |
|---------|---------------|-------------|----------------|
| PostgreSQL | `postgres:16-alpine` | `postgresql` | EnterpriseDB 16 |
| Redis | `redis:7-alpine` | `redis-server` | `redislite` (pip embed) |
| MySQL | `mysql:8` | `mysql-server` | — |
| MongoDB | `mongo:7` | `mongodb-org` | — |
| RabbitMQ | `rabbitmq:4` | `rabbitmq-server` | — |
| MariaDB | `mariadb:11` | `mariadb-server` | — |
| Elasticsearch | `elasticsearch:8` | — | — |
| ClickHouse | `clickhouse:24` | — | — |
| Neo4j | `neo4j:5` | — | — |

Each service gets a connection URL injected into `.env`. Services auto-start on first run.

### 3. Env Web UI

Opens an HTML form tunneled via cloudflared. Fill in API keys, database URLs, secrets from your browser. Values pre-filled from `.env` + `os.environ`. Works in Kaggle / Colab / headless. Ctrl+C to skip.

### 4. Smart Runner

- **Cleans requirements.txt**: strips version pins, replaces `psycopg2` → `psycopg2-binary`, removes malicious/typosquat packages (`install`, `setup`, `test`)
- **Detects imports**: scans all `.py` files with AST to find exactly what packages are needed
- **Installs individually**: if batch pip fails, installs detected packages one by one
- **AI fallback** (optional with API key): single-shot LLM call to fix remaining errors
- **Kills port conflicts**: `fuser -k` before starting
- **Generates restart.sh**: bash script to restart the project later

### Dashboard & Tunnels

Every open port gets a public `https://*.trycloudflare.com` URL:

```
📊 Dashboard:  https://dash-xxx.trycloudflare.com
🌐 App:        https://app-xxx.trycloudflare.com  (port 8000)
🐘 PostgreSQL: https://pg-xxx.trycloudflare.com   (port 5432)
```

Output includes PID, port, log path, and a `restart.sh` script.

## Usage

```bash
# Run any GitHub repo
runit https://github.com/user/repo

# Skip all prompts
runit https://github.com/user/repo --yes

# Run local project
runit /path/to/project

# Plain output (no ANSI/rich)
runit https://github.com/user/repo --plain

# With GitHub token for private repos
runit https://github.com/user/private-repo --token ghp_xxx
```

### In Kaggle / Colab

```python
!pip install --force-reinstall --no-cache-dir git+https://github.com/jaypaun007/runit.git

import os
os.environ["RUNIT_API_KEY"] = "sk-..."  # optional, enables AI fix

!runit https://github.com/user/repo --yes
```

All commands print with `! ` prefix for easy notebook copy-paste.

### AI Fix (optional)

Set an API key to enable single-shot error fixing when the deterministic runner fails:

```bash
export RUNIT_API_KEY="sk-..."
export RUNIT_PROVIDER="openai"       # or "anthropic", "custom"
export RUNIT_MODEL="gpt-4"
export RUNIT_BASE_URL="https://api.openai.com/v1"

runit --setup   # interactive wizard
runit --status  # current config
```

The AI fixer is a **single LLM call** (no agent loop). It sees the error, the project file list, and the run command. It outputs JSON: what to install and how to run.

## Architecture

```
runit/
├── runit/
│   ├── main.py              # CLI entry, arg parsing
│   ├── cli.py               # Terminal UI (rich + plain fallback)
│   ├── config.py            # Config & key management
│   ├── byok.py              # API key setup wizard
│   ├── llm.py               # AI client (OpenAI / Anthropic / custom)
│   ├── environment.py       # Platform detection (kaggle, colab, local)
│   ├── project_loader.py    # Git clone / local path resolver
│   ├── orchestrator.py      # 4-step pipeline with smart runner
│   ├── service_manager.py   # 3-tier service installer
│   ├── service_defs.py      # 9 service definitions
│   ├── env_resolver.py      # Smart .env resolver with random defaults
│   ├── process_monitor.py   # Background process manager
│   └── skills.py            # 20+ language skills & detection
├── PROMPT.md                # AI fixer system prompt
├── setup.py                 # v2.1.2 package
└── README.md
```

## Why Not Use Docker?

Docker isn't available on Kaggle, Colab, or many shared servers. Runit was designed for these environments. It installs services via `apt-get` or downloads standalone binaries. It also works fine with Docker when available.

## Why No AI Agent Loop?

Previous versions used a ReAct agent loop (20+ LLM calls per run). It was slow, expensive, and fragile. The current version:
- **Deterministic runner**: rule-based for 95% of cases, completes in seconds
- **AI fixer**: single LLM call for the remaining 5%, triggers only on failure
- **Result**: 10-100x faster, near-zero API cost for working projects

## Comparison

| Feature | v1.x | v2.0 | v2.1.2 |
|---------|------|------|--------|
| Analysis | AI-driven | Rule-based | Rule-based |
| Setup time | 2-5 min | 10-30s | 5-15s |
| LLM calls per run | 20-50 | 0 | 0-1 |
| Docker required | Yes | No | No |
| Kaggle/Colab | Broken | Works | Works + env web UI |
| Port tunnels | None | First port | All ports |
| Smart install | No | Batch pip | Import-based + unpin |

## Development

```bash
git clone https://github.com/jaypaun007/runit.git
cd runit
pip install -e ".[dev]"
```

## License

MIT — see [LICENSE](LICENSE).

---

*Made by [Jay Paun](https://github.com/jaypaun007)*

[GitHub](https://github.com/jaypaun007/runit) | [Issues](https://github.com/jaypaun007/runit/issues)
