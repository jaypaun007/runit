# ⚡ Runit — AI-Powered Project Runner

**Zero-config, zero-Docker project runner. Clone, setup, and run any GitHub repo in a single command. Works everywhere — Kaggle, Colab, headless servers, your laptop.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20Kaggle%20|%20Colab-lightgrey.svg)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]()
[![Maintenance](https://img.shields.io/badge/maintenance-active-brightgreen.svg)]()
[![GitHub last commit](https://img.shields.io/github/last-commit/jaypaun007/runit)]()

> **Runit** turns `git clone && cd && read README && install deps && configure env && setup services && run` into **one command**. No Docker. No TTY. No manual setup.

---

## One Command

```bash
pip install git+https://github.com/jaypaun007/runit.git
runit https://github.com/theopenco/llmgateway --yes
```

That's it. Runit clones the repo, reads the code, installs dependencies (pip/npm/pnpm/yarn), starts services (PostgreSQL, Redis, etc.), resolves env vars, builds, runs, and exposes every open port via cloudflared tunnels.

---

## Use Cases

| Where | How |
|-------|-----|
| **Kaggle/Colab** | `!runit https://github.com/user/repo --yes` — runs in background, shows public URLs |
| **Headless VPS** | `runit https://github.com/user/repo --yes` — no TTY needed |
| **Local dev** | `runit https://github.com/user/repo` — interactive prompts for API keys |
| **Existing project** | `runit .` or `runit /path/to/project` |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  runit https://github.com/user/repo                             │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────────────┐  │
│  │ Analyze  │ → │ Services │ → │   Agent Runtime (AI)      │  │
│  │          │   │          │   │  • read code + README      │  │
│  │ detect   │   │ install  │   │  • install deps on demand  │  │
│  │ language │   │ postgres │   │  • build                   │  │
│  │ services │   │ redis    │   │  • configure env vars      │  │
│  │ .env     │   │ mysql    │   │  • run project             │  │
│  └──────────┘   └──────────┘   │  • detect all ports        │  │
│                                 │  • verify it works         │  │
│                                 └──────────┬────────────────┘  │
│                                            ↓                   │
│                                 ┌────────────────────────┐     │
│                                 │  Dashboard + Tunnels   │     │
│                                 │  • cloudflared URLs    │     │
│                                 │  • all open ports      │     │
│                                 │  • service credentials  │     │
│                                 │  • live logs           │     │
│                                 └────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 1. Analyze (deterministic)
Detects language, package manager, services needed, env vars — all rule-based, no AI token cost.

### 2. Services (deterministic)
Installs required services with a 3-tier fallback chain:

| Service | Tier 1: Docker | Tier 2: apt-get | Tier 3: Binary |
|---------|---------------|-----------------|----------------|
| PostgreSQL | `postgres:16-alpine` | `postgresql` | EnterpriseDB 16 (40MB) |
| Redis | `redis:7-alpine` | `redis-server` | redislite (pip embed) |
| MySQL | `mysql:8` | `mysql-server` | — |
| MongoDB | `mongo:7` | `mongodb-org` | — |
| RabbitMQ | `rabbitmq:4` | `rabbitmq-server` | — |
| MariaDB | `mariadb:11` | `mariadb-server` | — |
| Nginx | `nginx:alpine` | `nginx` | — |
| SQLite | — | — | Built-in |
| Elasticsearch | `elasticsearch:8` | — | — |
| ClickHouse | `clickhouse:24` | — | — |
| Neo4j | `neo4j:5` | — | — |

Each service outputs its connection URL and credentials.

### 3. Agent Runtime (AI-driven)
An autonomous AI agent takes over with full system access:

1. **Reads** the project — README, config files, source code
2. **Decides** what to install, build, and configure — on demand, no pre-planned pipeline
3. **Installs** dependencies — pip, npm, pnpm, yarn, apt-get, whatever the project needs
4. **Builds** if needed — `npm run build`, `python setup.py build`, custom commands
5. **Configures** env vars — passes through existing values, asks for API keys
6. **Runs** the project — starts in background, captures PID
7. **Verifies** it works — checks logs, hits endpoints
8. **Reports** all open ports, PIDs, and logs

The agent has access to: file read/write/edit/delete, shell commands, web search, port detection, service install, and user prompts. It doesn't follow a fixed plan — it adapts based on what it finds.

### Dashboard & Tunnels

Every running port gets a public `https://*.trycloudflare.com` URL:

```
📊 Dashboard:  https://dash-xxx.trycloudflare.com
🌐 App:        https://app-xxx.trycloudflare.com  (port 3000)
🐘 PostgreSQL: https://pg-xxx.trycloudflare.com   (port 5432)
📋 Logs:       live streaming
```

---

## Installation

```bash
# Latest (recommended)
pip install git+https://github.com/jaypaun007/runit.git

# In Kaggle/Colab
!pip install --force-reinstall --no-cache-dir git+https://github.com/jaypaun007/runit.git
```

### Kaggle / Colab setup

```python
!pip install --force-reinstall --no-cache-dir git+https://github.com/jaypaun007/runit.git

import os
os.environ["RUNIT_API_KEY"] = "sk-your-api-key"    # Optional — enables AI agent
os.environ["RUNIT_PROVIDER"] = "custom"
os.environ["RUNIT_MODEL"] = "model-name"
os.environ["RUNIT_BASE_URL"] = "https://api.example.com/v1"

!runit https://github.com/theopenco/llmgateway --yes
```

---

## Configuration

```bash
# Interactive wizard
runit --setup

# Environment variables
export RUNIT_API_KEY="sk-..."
export RUNIT_PROVIDER="custom"
export RUNIT_MODEL="gpt-4"
export RUNIT_BASE_URL="https://api.openai.com/v1"

# Check config
runit --status
```

Config file: `~/.runit/config.json`

### Flags

| Flag | Description |
|------|-------------|
| `--yes` | Skip all prompts (auto-confirm) |
| `--plain` | Disable colored output |
| `--setup` | Interactive config wizard |
| `--status` | Show current config and status |
| `--skills` | List available agent skills |
| `--max-steps N` | Max agent steps (default: 20) |

---

## Architecture

```
runit/
├── runit/
│   ├── main.py             # CLI entry point
│   ├── cli.py              # Terminal UI (rich + plain fallback)
│   ├── config.py           # Config & key management
│   ├── llm.py              # AI client (OpenAI / custom)
│   ├── environment.py      # Platform detection
│   ├── project_loader.py   # Clone repos, git pull
│   ├── orchestrator.py     # 4-step pipeline: analyze → services → env UI → agent
│   ├── service_manager.py  # 3-tier service install (Docker → apt → binary)
│   ├── service_defs.py     # 11 service definitions with credentials
│   ├── env_resolver.py     # Smart .env resolution
│   ├── process_monitor.py  # Background process runner + port scanner
│   ├── agent_core.py       # ReAct loop with dedup protection
│   ├── agent_tools.py      # 27 tools: read, write, edit, delete, search, run, detect
│   ├── agent_prompts.py    # System prompts for agent-driven runtime
│   ├── web_tools.py        # Web search + GitHub README fetch
│   └── skills.py           # Language skills & framework detection
├── setup.py                # v2.1.2 installer
├── README.md               # This file
├── LICENSE                 # MIT
└── .gitignore
```

---

## Why This Approach?

| Aspect | v1.x (Pure Agent) | v2.0 (Deterministic) | v2.1.2 (Hybrid) |
|--------|-------------------|---------------------|-----------------|
| Analysis | AI decides everything | Rule-based only | Rule-based (free) |
| Services | Docker-required | apt / binary | apt / binary + credentials |
| Env vars | Manual prompting | Auto-fill + web UI + AI | Pass-through + web UI for critical |
| Runtime | Agent plans everything | Fixed 5-step pipeline | Agent adapts on-demand |
| Ports | None | First port only | All ports tunneled |
| Speed | Slow (looping) | Fast | Fast (agent only at runtime) |
| Token cost | High | Low | Low (runtime only) |
| Docker | Required | Optional | Optional |
| Kaggle/Colab | Broken | Works | Works |

**v2.1.2 gives the AI agent freedom at runtime but keeps the web UI for env vars — best of both worlds.**

---

## Development

```bash
git clone https://github.com/jaypaun007/runit.git
cd runit
pip install -e ".[dev]"
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Made by [Jay Paun](https://github.com/jaypaun007)*

**Keywords:** project runner, AI agent, zero-config, no Docker, GitHub runner, Kaggle, Colab, cloudflared, PostgreSQL, Redis, autonomous setup, dev tool

[GitHub](https://github.com/jaypaun007/runit) | [Issues](https://github.com/jaypaun007/runit/issues) | [Discussions](https://github.com/jaypaun007/runit/discussions)
