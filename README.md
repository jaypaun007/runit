# ⚡ Runit v2.0

**Deterministic project runner — clone, setup, and run any GitHub repo in one command. No Docker required.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20Kaggle%20|%20Colab-lightgrey.svg)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]()

---

## One Command

```bash
pip install git+https://github.com/jaypaun007/runit.git
runit https://github.com/theopenco/llmgateway --yes
```

---

## What is Runit?

Runit is an **AI-powered project runner** that turns `git clone && cd && read README && install deps && configure env && setup services && run` into a single command.

**v2.0 is a complete rewrite** with a deterministic 5-step pipeline:

```
[1/5] Analyze   →  Read project structure, detect language, services, env vars
[2/5] Services  →  Install PostgreSQL, Redis, MySQL, etc. without Docker
[3/5] Env       →  Resolve .env vars (auto-fill, web UI, or AI generation)
[4/5] Deps      →  Install dependencies (pip, npm, pnpm, etc.)
[5/5] Run       →  Start the project, detect ports, expose via cloudflared
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Zero Docker** | PostgreSQL runs via apt/binary, Redis via redislite — works in Kaggle/Colab |
| **Deterministic** | No unpredictable agent loops. AI only for error recovery |
| **Cloud-native** | Works in Kaggle, Colab, and headless servers — no TTY required |
| **Web UI for .env** | Fill env vars through a browser form tunneled via cloudflared |
| **Public URLs** | All running ports get cloudflared trycloudflare.com URLs |
| **AI Planner** | Reads README + code files, plans the full pipeline before executing |
| **Live Dashboard** | Web page listing all services, ports, and public URLs |
| **Smart env resolution** | 100+ critical patterns; service URLs auto-filled; secrets prompted or AI-generated |
| **3-tier service install** | Docker → apt-get → binary download (postgres 40MB binary for cloud) |
| **Persistent projects** | Clones to `./<repo-name>/` with `git pull --ff-only` on re-run |

---

## Installation

### macOS / Linux / Kaggle

```bash
pip install git+https://github.com/jaypaun007/runit.git
```

### Kaggle / Colab

```python
!pip install --force-reinstall --no-cache-dir git+https://github.com/jaypaun007/runit.git

import os
os.environ["RUNIT_API_KEY"] = "sk-your-api-key"
os.environ["RUNIT_PROVIDER"] = "custom"
os.environ["RUNIT_MODEL"] = "gpt-4"
os.environ["RUNIT_BASE_URL"] = "https://api.example.com/v1"

!runit https://github.com/theopenco/llmgateway --yes
```

---

## Usage

```bash
# Run a GitHub repo (auto-detect everything)
runit https://github.com/user/repo

# Run with auto-confirm (headless / Kaggle)
runit https://github.com/user/repo --yes

# Run a local project
runit /path/to/project
runit .

# With AI provider configured — better analysis
runit https://github.com/user/repo
```

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

## How It Works

### Pipeline

```
runit https://github.com/user/repo
│
├─ [0] AI Planner (optional)
│     Reads README + code → generates setup plan
│
├─ [1] Analyze
│     Detect language, package manager, services, .env.example
│
├─ [2] Services
│     Install PostgreSQL / Redis / MySQL / etc.
│     Tier 1: Docker  →  Tier 2: apt-get  →  Tier 3: binary download
│
├─ [3] Env Variables
│     Read .env.example → resolve each var:
│       • Already set in environment → keep
│       • Matches running service → auto-fill URL
│       • Critical/secret → show web UI form (notebook) or prompt (terminal)
│       • Has example value → use it
│       • Everything else → random sensible default
│     AI generation (--yes + API key) → realistic format-correct values
│
├─ [4] Dependencies
│     pip install / npm install / pnpm install / etc.
│     Auto-installs pnpm/yarn if missing, falls back to npm
│
├─ [5] Run
│     Start project → detect port → cloudflared tunnel → dashboard
│
└─ [✓] Dashboard
      Public URL │ Local URL │ Services │ Ports │ Log
      📊 Web dashboard at https://*.trycloudflare.com
```

### AI Planner (Step 0)

When an API key is configured, Runit reads the project's README, package.json, requirements.txt, .env.example, docker-compose.yml, and other files. It asks the LLM to generate a structured plan:

```json
{
  "project_type": "node",
  "package_manager": "pnpm",
  "services": ["redis", "postgresql"],
  "run_command": "pnpm run dev",
  "description": "LLM Gateway API proxy"
}
```

The plan replaces auto-detection for a more informed setup.

### Services (No Docker Required)

Runit installs services using a 3-tier fallback:

| Service | Docker | apt-get | Binary Fallback |
|---------|--------|---------|-----------------|
| PostgreSQL | `postgres:16-alpine` | `postgresql` | EnterpriseDB 16 binary (40MB) |
| Redis | `redis:7-alpine` | `redis-server` | redislite (pip embed) |
| MySQL | `mysql:8` | `mysql-server` | — |
| MongoDB | `mongo:7` | `mongodb-org` | — |
| RabbitMQ | `rabbitmq:4` | `rabbitmq-server` | — |
| MariaDB | `mariadb:11` | `mariadb-server` | — |
| Nginx | `nginx:alpine` | `nginx` | — |
| SQLite | — | — | Built-in (no install) |
| Elasticsearch | `elasticsearch:8` | — | — |
| ClickHouse | `clickhouse:24` | — | — |
| Neo4j | `neo4j:5` | — | — |

### Environment Variables

Runit resolves `.env.example` variables intelligently:

1. **Already in `os.environ`** → keep as-is
2. **Matches a running service** → auto-fill connection URL (e.g., `DATABASE_URL` → `postgresql://app:app@localhost:5432/app`)
3. **Critical/secret** (API keys, passwords, tokens) → in notebooks: show **web UI form** tunneled via cloudflared; in terminal: prompt with `input()`
4. **Has example value** → use the example
5. **Everything else** → random sensible default (localhost for hosts, random port, random strings for secrets)

With `--yes` + API key, AI generates format-correct placeholder values (e.g., `OPENAI_API_KEY` → `sk-proj-...`).

### Public Tunnels (cloudflared)

Every running port gets a public `https://*.trycloudflare.com` URL:

- App server → public URL in dashboard
- PostgreSQL → public URL for remote connections
- Dashboard → web UI listing all services and ports

Cloudflared is auto-downloaded if missing.

---

## Architecture

```
runit/
├── runit/
│   ├── main.py             # CLI entry point
│   ├── cli.py              # Terminal UI (rich + plain fallback)
│   ├── config.py           # Config & key management
│   ├── llm.py              # AI client (OpenAI / Anthropic / custom)
│   ├── environment.py      # Platform detection
│   ├── project_loader.py   # Clone repos, git pull
│   ├── orchestrator.py     # Pipeline: plan → analyze → services → env → deps → run
│   ├── service_manager.py  # 3-tier service install
│   ├── service_defs.py     # 11 service definitions
│   ├── env_resolver.py     # Smart .env resolution
│   ├── process_monitor.py  # Background process runner
│   ├── error_classifier.py # 17 error types + auto-healers
│   ├── agent_core.py       # ReAct loop with dedup protection
│   ├── agent_tools.py      # 23 tools: read, write, install, run
│   ├── agent_prompts.py    # System prompts for agent
│   ├── skills.py           # Language skills & framework detection
│   └── executor.py         # Runtime checker
├── setup.py                # v2.0.1 installer
├── README.md               # This file
├── LICENSE                 # MIT
└── .gitignore
```

---

## Configuration

```bash
# Interactive setup
runit --setup

# Or via environment variables
export RUNIT_API_KEY="sk-..."
export RUNIT_PROVIDER="custom"
export RUNIT_MODEL="gpt-4"
export RUNIT_BASE_URL="https://api.openai.com/v1"

# View status
runit --status
```

Config file: `~/.runit/config.json`

---

## Why v2.0?

The original v1.x used a pure agent architecture — the AI decided everything. This caused:

- **Infinite loops**: The agent called `research_project` repeatedly on the same repo
- **Unpredictable results**: Different runs gave different outcomes
- **Docker dependency**: Required Docker for services, breaking Kaggle/Colab
- **Slow**: Agent deliberation for every step

**v2.0 is the opposite**: deterministic pipeline for the 80% case, AI only for the 20% error case. Services install without Docker. Everything works in cloud notebooks.

---

## Comparison: v1.x vs v2.0

| Aspect | v1.x | v2.0 |
|--------|------|------|
| Architecture | Pure agent (unpredictable) | Deterministic pipeline |
| Docker requirement | Required | Optional (3-tier fallback) |
| Kaggle/Colab | Broken | First-class support |
| .env resolution | Manual prompting | Auto-fill + web UI + AI |
| Services | Docker only | Docker → apt → binary |
| Port exposure | None | cloudflared public URLs |
| Speed | Slow (agent deliberation) | Fast (direct execution) |
| Reproducibility | Low | High |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Made by [Jay Paun](https://github.com/jaypaun007)*

[GitHub](https://github.com/jaypaun007/runit) | [Issues](https://github.com/jaypaun007/runit/issues) | [Discussions](https://github.com/jaypaun007/runit/discussions)
