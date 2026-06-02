<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://via.placeholder.com/800x200/1a1a2e/00d4ff?text=⚡+Runit">
    <img src="https://via.placeholder.com/800x200/ffffff/1a1a2e?text=⚡+Runit" alt="Runit Banner" width="100%">
  </picture>
</p>

<div align="center">

# ⚡ Runit

**AI-powered agent that makes any GitHub repo runnable — automatically.**

No manual setup. No dependency hunting. No config files. **Just run.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-macOS%20|%20Linux%20|%20Windows-lightgrey.svg)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/jaypaun007/runit?style=social)]()
[![GitHub forks](https://img.shields.io/github/forks/jaypaun007/runit?style=social)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

---

### 📋 **Table of Contents**

[Installation](#-installation) •
[Quick Start](#-quick-start) •
[Usage](#-usage) •
[How It Works](#-how-it-works) •
[Agent Skills](#-agent-skills) •
[Debugger](#-advanced-debugger) •
[BYOK](#-bring-your-own-key-byok) •
[How-To Guides](#-how-to-guides) •
[Configuration](#-configuration) •
[Contributing](#-contributing) •
[License](#-license)

---

## 🚀 Quick Start

```bash
# One command — that's it
runit https://github.com/user/repo

# Or run your local project
runit .
```

> 🎯 **1 command. 0 config. Any repo. Any language.**

---

## ✨ Features

- **🔌 One-command execution** — `runit https://github.com/user/repo`
- **🧠 AI-powered analysis** — understands project structure, finds entry points
- **📦 Smart dependency installation** — installs only what's needed per project type
- **🔄 Auto error recovery** — detects failures, fixes them, retries persistently
- **🔑 BYOK (Bring Your Own Key)** — works with OpenAI, Anthropic, or any custom endpoint
- **🛠️ Agent Skills system** — 17 specialized handlers for all major languages
- **🐛 Advanced Debugger** — deep error analysis, category classification, code patch suggestions
- **📝 Code Fix Suggestions** — detects issues and suggests or applies code patches
- **💬 User Instructions** — optionally tell Runit how to run your project
- **🔔 Installation notifications** — desktop alerts on install status
- **🎨 Beautiful CLI** — colored output with rich formatting and credits
- **🌍 Cross-platform** — macOS, Linux, Windows, Kaggle, Google Colab
- **🔄 Persistent retry** — keeps trying with escalating strategies until project runs
- **🔐 Private repo support** — authenticate with `--token` or `GITHUB_TOKEN`
- **🔑 Key management** — store API keys/tokens locally with `runit --key-add`
- **🗄️ Env var scanning** — detects required environment variables from source code
- **🌐 Web research** — searches the web for error solutions when stuck
- **📖 GitHub README reader** — fetches README without cloning for better analysis
- **🛡️ Safe** — never modifies user code, only installs dependencies
- **❤️ Made by Jay Paun**

---

## 📦 Installation

### macOS / Linux

```bash
# One-liner (clone + install)
git clone https://github.com/jaypaun007/runit.git
cd runit
chmod +x install.sh && ./install.sh

# Or via pip directly
pip install git+https://github.com/jaypaun007/runit.git
```

### Windows (PowerShell)

```powershell
# One-liner
git clone https://github.com/jaypaun007/runit.git
cd runit
.\install.ps1

# Or via pip directly
pip install git+https://github.com/jaypaun007/runit.git
```

### Kaggle / Google Colab

Runit auto-detects Kaggle and Colab environments and optimizes execution:

```bash
# Works out of the box in Kaggle/Colab
!git clone https://github.com/jaypaun007/runit.git
%cd runit
!pip install -e .
!runit https://github.com/user/some-project
```

### Quick install with pip

```bash
pip install runit
```

---

## 🚀 Usage

### Run a GitHub repository

```bash
runit https://github.com/user/some-project
```

### Run a private GitHub repository

```bash
runit https://github.com/user/private-repo --token ghp_xxxxxxxxxxxx
# Or set env: export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

### Run a local folder

```bash
runit /path/to/project
runit .                        # current directory
```

### First-time setup — configure your API key

```bash
runit --setup
```

Interactive wizard guides you through provider selection:

```
  ╔══════════════════════════════════════╗
  ║       ⚡ Runit v1.0.0               ║
  ║  AI-Powered Repo Execution Agent     ║
  ╚══════════════════════════════════════╝

  🔑 Bring Your Own Key (BYOK) Setup
  ┌──────────────────────────────────────────────┐
  │ Configure your AI provider to power Runit's  │
  │ analysis engine.                             │
  └──────────────────────────────────────────────┘

  Supported providers:
    openai       - OpenAI
    anthropic    - Anthropic
    custom       - Custom Endpoint
```

### View configuration status

```bash
runit --status
```

### List available agent skills

```bash
runit --skills
```

### Manage stored keys (API keys, tokens for projects)

```bash
runit --key-list              # List all stored keys
runit --key-add MY_API_KEY    # Store a new key (prompts for value)
runit --key-delete MY_API_KEY # Delete a stored key
```

---

## 🔑 Bring Your Own Key (BYOK)

Runit uses AI only for **understanding projects** and **fixing errors** — not for running code. You bring your own API key from any provider.

### Supported Providers

| Provider    | Default Model       | Custom Endpoint Support |
|-------------|---------------------|------------------------|
| OpenAI      | gpt-4               | ✅ Any OpenAI-compatible API |
| Anthropic   | claude-3-5-sonnet   | ✅ Any Anthropic-compatible API |
| Custom      | user-defined        | ✅ Any OpenAI-compatible endpoint |

### Environment Variables

```bash
export RUNIT_API_KEY="sk-..."       # API key
export RUNIT_BASE_URL="..."          # Custom endpoint URL
export RUNIT_MODEL="gpt-4"           # Model override
export RUNIT_PROVIDER="openai"       # Provider override
```

### Custom Endpoints

Use any OpenAI-compatible API (Ollama, LocalAI, vLLM, etc.):

```bash
runit --setup
# Select "custom" as provider
# Enter your endpoint URL
# Enter your model name
```

Or via environment:

```bash
export RUNIT_API_KEY="not-needed"
export RUNIT_BASE_URL="http://localhost:1234/v1"
export RUNIT_MODEL="local-model"
export RUNIT_PROVIDER="custom"
```

> **No API key?** Runit still works with limited fallback analysis.

---

## 🌐 Web Research & Auto-Search

When Runit encounters an error it can't fix automatically, it can search the web for solutions:

```bash
# Automatic: Runit searches the web when stuck
runit https://github.com/user/project

# Manual: Use the "web:search query" option when prompted
# At the "Your input" prompt, type:
web:how to fix ModuleNotFoundError in this project
```

Runit also:
- Fetches GitHub READMEs without cloning for better analysis
- Searches error messages online for solutions
- Displays relevant StackOverflow / GitHub Issues results

---

## ☁️ Kaggle / Google Colab

Runit automatically detects when running on **Kaggle** or **Google Colab**:

```python
# In a Kaggle/Colab notebook:
!pip install runit
!runit https://github.com/user/repo
```

What changes in cloud mode:
- No Docker requirement — runs source code directly
- Aggressive retry strategy
- Optimized dependency installation for restricted environments
- Auto-detects missing `git`, `npm`, etc. and adapts

---

## 🔐 Private Repository Support

Access private GitHub repos with a personal access token:

```bash
# Via CLI flag
runit https://github.com/org/private-repo --token ghp_xxxxxxxx

# Via environment variable
export GITHUB_TOKEN=ghp_xxxxxxxx
runit https://github.com/org/private-repo

# Via setup wizard
runit --setup  # Then configure GitHub token
```

Tokens can be stored permanently:
- Set during `runit --setup`
- Added later by editing `~/.runit/config.json`
- Passed via `GITHUB_TOKEN` or `GH_TOKEN` env vars

---

## 🛠️ Agent Skills

Runit ships with **17 specialized agent skills** covering all major programming languages. Each skill knows exactly how to detect, install, and run its project type.

### Core Skills

| Skill               | Detects                                    | Installs              | Runs                     |
|---------------------|--------------------------------------------|-----------------------|--------------------------|
| 🐍 Python Expert    | requirements.txt, setup.py, pyproject.toml | pip install           | python \<entry\>         |
| 🟢 Node.js Expert   | package.json, yarn.lock, pnpm-lock.yaml    | npm/pnpm/yarn install | node \<entry\>           |
| 🦀 Rust Expert      | Cargo.toml                                 | cargo build           | cargo run                |
| 🔵 Go Expert        | go.mod, go.sum                             | go mod download       | go run .                 |
| 💎 Ruby Expert      | Gemfile, Gemfile.lock                      | bundle install        | ruby \<entry\>           |
| 🦕 Deno Expert      | deno.json, deno.jsonc                      | —                     | deno run                 |
| ☕ Java Expert      | pom.xml, build.gradle                      | —                     | mvn compile              |

### New Skills (v1.1)

| Skill                     | Detects                                          | Installs               | Runs                        |
|---------------------------|--------------------------------------------------|------------------------|-----------------------------|
| ⚙️ C/C++ Expert           | CMakeLists.txt, Makefile, configure               | cmake / make           | make / cmake && make        |
| 🔷 C# / .NET Expert       | \*.csproj, \*.sln                                | dotnet restore         | dotnet run                  |
| 🐘 PHP Expert             | composer.json, composer.lock                     | composer install       | php -S localhost:8000       |
| 🟣 Kotlin Expert          | \*.kt, build.gradle.kts                          | gradle build           | gradle run / kotlinc        |
| 🎯 Dart/Flutter Expert    | pubspec.yaml                                     | dart/pub get           | dart run / flutter run      |
| 📊 R Expert               | DESCRIPTION, \*.Rproj                            | renv::restore()        | Rscript \<entry\>           |
| 🔬 Julia Expert           | Project.toml, Manifest.toml                      | Pkg.instantiate()      | julia \<entry\>             |
| 🌙 Lua Expert             | \*.rockspec, \*.lua                              | luarocks install       | lua \<entry\>               |
| 🔺 Scala Expert           | build.sbt, \*.scala                              | sbt update             | sbt run                     |
| 💧 Elixir Expert          | mix.exs                                          | mix deps.get           | mix run                     |

Skills are auto-selected based on project detection. View them with:

```bash
runit --skills
```

---

## 🐛 Advanced Debugger

Runit v1.1 includes a built-in **Advanced Debugger Agent** that analyzes runtime errors using multiple strategies:

### What It Does

1. **Error Classification** — categorizes errors into types: missing API keys, port conflicts, network issues, permissions, disk space, memory, version mismatches, dependency conflicts, and config errors
2. **Language Detection** — identifies the programming language from error message patterns (Python, Node.js, Rust, Go, Ruby, etc.)
3. **Module Error Extraction** — pinpoints missing modules/packages across all supported languages
4. **Syntax Error Analysis** — extracts structured syntax error info from compiler/interpreter output
5. **Config Issue Detection** — checks project files for common misconfigurations (missing .env, uninitialized package managers)
6. **Code Patch Suggestions** — suggests specific fixes for port conflicts, missing modules, permission issues
7. **AI-Powered Deep Analysis** — when API key is configured, uses AI for complex error diagnosis
8. **Interactive Fixing** — can optionally apply suggested code patches to your project

### Example Debug Flow

```
Error: listen EADDRINUSE :::3000
  │
  ▼
┌─────────────────────────┐
│ Debugger Analysis       │
│                         │
│ • Category: Port Conflict│
│ • Language:  Node.js    │
│ • Port 3000 is in use   │
│ • Suggestion: set PORT=3001│
└─────────────────────────┘
  │
  ▼
Auto-fix: change PORT env var
  │
  ▼
Retry with new port... Success!
```

The debugger runs automatically on every error and displays a structured report before attempting fixes.

---

## 🧠 How It Works

```
  User input (repo / folder)
          │
          ▼
  ┌───────────────────────┐
  │  1. Project Loader    │  Clone repo / scan folder (GitHub token support)
  └─────────┬─────────────┘
            │
            ▼
  ┌───────────────────────┐
  │  2. AI Analysis       │  Understand project type, entry, deps, env vars
  └─────────┬─────────────┘
            │
            ▼
  ┌───────────────────────┐
  │  3. Skill Match       │  Load specialized agent skill
  └─────────┬─────────────┘
            │
            ▼
  ┌───────────────────────┐
  │  4. Install Deps      │  Install only required dependencies
  └─────────┬─────────────┘
            │
            ▼
  ┌───────────────────────┐
  │  5. Execute           │  Run the project
  └─────────┬─────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
   Success      Error ──► ┌─────────────────┐
                           │  6. AI Fix       │
                           │  + Web Research  │
                           │  + Env Detection │
                           └────────┬────────┘
                                    │
                          ┌─────────▼─────────┐
                          │   Escalation       │
                          │   Strategy 1:      │
                          │     Auto-fix       │
                          │   Strategy 2:      │
                          │     Ask for keys   │
                          │   Strategy 3:      │
                          │     .env setup     │
                          │   Strategy 4:      │
                          │     Web search     │
                          │   Strategy 5:      │
                          │     User help      │
                          └─────────┬─────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │  Retry (loops    │
                          │  until success   │
                          │  or user quits)  │
                          └─────────────────┘
```

### AI Usage Boundaries

| ✅ AI is used for               | ❌ AI is NOT used for         |
|--------------------------------|------------------------------|
| Understanding project structure | Running code                |
| Deciding entry point            | Replacing dependency manager |
| Fixing runtime errors           | System-level installation    |
| Generating execution plan       | Modifying user code          |

---

## 🏗️ Architecture

```
runit/
├── runit/
│   ├── __init__.py        # Package metadata
│   ├── main.py            # CLI orchestration & entry point
│   ├── cli.py             # Terminal UI (rich + fallback, credits)
│   ├── config.py          # Configuration + key management
│   ├── byok.py            # BYOK setup wizard
│   ├── llm.py             # AI client (OpenAI, Anthropic, custom)
│   ├── environment.py     # Kaggle/Colab detection, platform info
│   ├── web_tools.py       # Web search, GitHub API, error research
│   ├── project_loader.py  # Clone repos (public/private), scan folders
│   ├── analyzer.py        # AI analysis + env var scanning + web research
│   ├── skills.py          # Agent skill registry (17 languages)
│   ├── deps.py            # Smart dependency installer
│   ├── executor.py        # Project execution engine (env-aware)
│   ├── error_handler.py   # Error detection, auto-fix, web search
│   ├── debugger.py        # Advanced debugger + code fix suggestions
│   └── notify.py          # Desktop notifications
├── tests/                 # Test suite (65+ tests)
│   ├── test_config.py
│   ├── test_skills.py
│   ├── test_executor.py
│   ├── test_error_handler.py
│   ├── test_debugger.py
│   └── test_web_tools.py
├── setup.py               # Package installer
├── requirements.txt       # Python dependencies
├── install.sh             # macOS/Linux one-click installer
├── install.ps1            # Windows one-click installer
├── .gitignore
└── README.md
```

---

## ⚙️ Configuration

Config is stored at `~/.runit/config.json`:

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "api_key": "sk-...",
  "base_url": "https://api.openai.com/v1",
  "max_retries": 3,
  "notifications": true
}
```

Configure via:
- `runit --setup` (interactive wizard)
- Environment variables (see [BYOK section](#environment-variables))
- Direct file edit at `~/.runit/config.json`

---

## 📋 Examples

```bash
# Run a Python project from GitHub
runit https://github.com/tiangolo/fastapi

# Run a private GitHub repo
runit https://github.com/org/private-repo --token ghp_xxx

# Run a local Node.js project
runit ~/projects/my-node-app

# Run current directory
runit .

# Configure Anthropic Claude
runit --setup
# → Select "anthropic"
# → Enter your API key
# → Use default endpoint

# Use a local LLM (Ollama, LocalAI, etc.)
export RUNIT_BASE_URL="http://localhost:11434/v1"
export RUNIT_API_KEY="ollama"
export RUNIT_MODEL="llama3"
runit .

# Store an API key for a project
runit --key-add OPENAI_API_KEY

# List all stored keys
runit --key-list
```

---

## 💡 How-To Guides

### How to run any GitHub repo

```bash
# Public repo — one command
runit https://github.com/user/project

# Skip the disclaimer prompt (if you trust the source)
echo y | runit https://github.com/user/project

# With a specific retry limit
runit https://github.com/user/project --retries 5
```

### How to run with custom instructions

When running a project with special setup requirements:

```
$ runit .
  ...
  [2/6] ◉ Optional: Add custom instructions
  💬 Any special instructions for how to run this project?
     (e.g. 'use python3 instead of python', 'set --port 9000', 'cd backend first')
     ⏳ Press Enter to skip
  Instructions: use python3.11 instead of python3
  ✓ Noted: use python3.11 instead of python3
```

These instructions are recorded and passed to the AI analysis for better understanding.

### How to handle missing API keys

If a project needs API keys, Runit will:

1. **Auto-detect** required env vars from source code scanning
2. **Prompt upfront** — asks you to set them before first run
3. **Store securely** — saves to `~/.runit/keys.json` for reuse
4. **Prompt again** — if a key is missing at runtime, you'll be asked

```
  🔑 This project requires 2 environment variable(s)
    🔑 OPENAI_API_KEY
    🔑 DATABASE_URL
  Set these now? [Y/n]: y
  🔑 Project requires: OPENAI_API_KEY
  Enter value for OPENAI_API_KEY: [hidden]
  ✓ OPENAI_API_KEY set
```

### How to run a private repo

```bash
# Option 1: pass --token
runit https://github.com/org/private-repo --token ghp_xxxxxxxxxxxxxxxxxxxx

# Option 2: set env var
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
runit https://github.com/org/private-repo

# Option 3: configure permanently
runit --setup  # Then configure GitHub token when prompted
```

### How to use Docker mode

```bash
# Auto-detect Docker support
runit https://github.com/user/project

# Skip mode prompt and force Docker
runit https://github.com/user/project --docker

# Skip mode prompt and force dev mode
runit https://github.com/user/project --dev
```

When using Docker, Runit auto-detects:
- Exposed ports from `Dockerfile` (`EXPOSE` directives)
- Port mappings from `docker-compose.yml`
- Docker image from README badges

### How to set up your AI provider

```bash
# Interactive setup wizard
runit --setup

# Or use environment variables
export RUNIT_PROVIDER=openai
export RUNIT_API_KEY=sk-...
export RUNIT_MODEL=gpt-4
runit .
```

### How to manage stored keys

```bash
# Store an API key for a project
runit --key-add OPENAI_API_KEY

# List all stored keys
runit --key-list

# Delete a stored key
runit --key-delete OLD_API_KEY
```

### How to view available skills

```bash
runit --skills
```

Shows all 17 agent skills with descriptions and detection files.

### How to check your configuration

```bash
runit --status
```

Displays provider, model, API key status, GitHub token, retry count, and stored keys.

### How to run on Kaggle / Google Colab

```python
# In a notebook cell:
!pip install runit
!runit https://github.com/user/project
```

Runit auto-detects Kaggle and Colab environments and optimizes execution.

---

## 🛡️ Safety Rules

- **Never** deletes or overwrites user code
- **Only** modifies the runtime environment (dependencies, environment variables)
- **Never** runs destructive system commands
- **Always** asks before modifying project files (when applicable)

---

## 🌟 Show Your Support

If Runit helps you, consider giving it a ⭐ on GitHub!  
Every star helps more developers discover the project.

---

## 🤝 Contributing

**Contributions are welcome!** Runit is an open-source project and we'd love your help making it better.

### Ways to Contribute

- 🐛 **Report bugs** — Open an [issue](https://github.com/jaypaun007/runit/issues) with details
- 💡 **Suggest features** — Share your ideas in [discussions](https://github.com/jaypaun007/runit/discussions)
- 🔧 **Submit PRs** — Fix bugs, add skills, improve the debugger, write tests
- 📖 **Improve docs** — Better README, more examples, clearer guides
- 🌍 **Add a skill** — Support a new language/project type
- 🧪 **Write tests** — Help us reach 100% coverage

### Getting Started

```bash
# Fork the repo, then:
git clone https://github.com/your-username/runit.git
cd runit
pip install -e ".[dev]"
python -m pytest tests/
```

### Code of Conduct

Be respectful, inclusive, and constructive. Runit is a community project — everyone is welcome.

### Project Roadmap

- [x] Core execution engine (Python, Node, Rust, Go, Ruby, Deno, Java)
- [x] 10 new language skills (C/C++, C#, PHP, Kotlin, Dart, R, Julia, Lua, Scala, Elixir)
- [x] Advanced debugger with code fix suggestions
- [x] Docker mode with port auto-detection
- [x] Web research & error auto-search
- [x] BYOK (Bring Your Own Key) — any AI provider
- [ ] GitHub Actions CI/CD pipeline
- [ ] PyPI package publish
- [ ] VS Code extension
- [ ] Web UI dashboard
- [ ] Windows native installer
- [ ] 100% test coverage

---

## ⚠️ Disclaimer

Runit is provided for **educational and research purposes only**. By using this tool, you acknowledge and agree that:

- Running arbitrary code from unknown sources carries inherent security risks
- You are responsible for reviewing any code before executing it
- The authors assume **no liability** for any damage, data loss, or security breaches resulting from use of this tool
- This tool should only be used in isolated environments (containers, VMs, or sandboxes) when evaluating untrusted code
- You assume **all risk** associated with executing third-party projects

---

## 📄 License

MIT

---

<div align="center">
  <p>Made with ❤️ by <strong><a href="https://github.com/jaypaun007">Jay Paun</a></strong></p>
  <p>
    <a href="https://github.com/jaypaun007/runit">🏠 Home</a> •
    <a href="https://github.com/jaypaun007/runit/issues">🐛 Report Bug</a> •
    <a href="https://github.com/jaypaun007/runit/discussions">💡 Feature Request</a> •
    <a href="https://github.com/jaypaun007/runit/pulls">🔧 Submit PR</a> •
    <a href="https://github.com/jaypaun007/runit/stargazers">⭐ Star</a>
  </p>
  <p>
    <sub>Built with Python • Powered by AI • Driven by community</sub>
  </p>
  <p>
    <a href="https://star-history.com/#jaypaun007/runit&Date">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=jaypaun007/runit&type=Date&theme=dark" />
        <img src="https://api.star-history.com/svg?repos=jaypaun007/runit&type=Date" alt="Star History Chart" width="600" />
      </picture>
    </a>
  </p>
  <br>
  <p>
    <strong>If you find this project useful, please ⭐ star it on GitHub!</strong>
  </p>
  <br>
  <p>
    <sub>Runit is provided for educational purposes. Use responsibly.</sub>
  </p>
</div>
