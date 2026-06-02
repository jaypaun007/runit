import os
import re
import random
import string
from pathlib import Path

from runit.service_manager import service_name_from_env

CRITICAL_ENV_PATTERNS = [
    "api_key", "api_secret", "password", "secret_key",
    "private_key", "auth_token", "jwt_secret",
    "encryption_key", "webhook_secret",
    "stripe_secret", "openai_api_key", "anthropic_api_key",
    "github_token", "slack_token", "discord_token",
    "groq_api_key", "grok_api_key", "claude_api_key",
    "gemini_api_key", "perplexity_api_key",
    "cohere_api_key", "mistral_api_key",
    "replicate_api_token", "huggingface_token",
    "elevenlabs_api_key", "deepgram_api_key",
    "pinecone_api_key", "qdrant_api_key",
    "weaviate_api_key", "algolia_api_key",
    "supabase_key", "firebase_private_key",
    "sendgrid_api_key", "mailgun_api_key",
    "postmark_api_token", "twilio_auth_token",
    "aws_secret_access_key", "gcp_service_account",
    "azure_connection_string", "s3_secret_key",
    "resend_api_key", "llmgateway_api_key",
    "gateway_api_key", "database_url",
    "mongodb_uri", "redis_url",
]


def is_critical(var_name: str) -> bool:
    lower = var_name.lower()
    for pat in CRITICAL_ENV_PATTERNS:
        if pat in lower:
            return True
    return False


class EnvResolver:
    def __init__(self, project_path: str, service_manager=None):
        self.project_path = Path(project_path)
        self.service_manager = service_manager
        self.env = {}
        self.categories = {}

    def scan_env_example(self) -> dict[str, str]:
        for name in (".env.example", ".env.sample", "env.example"):
            path = self.project_path / name
            if path.exists():
                return self._parse_env_file(path)
        return {}

    def scan_source_code(self) -> list[str]:
        env_vars = set()
        patterns = [
            r'(?:process\.env|os\.environ(?:\[|\.get\())["\'](\w+)["\')]',
            r'env\(["\'](\w+)["\']\)',
            r'config\(["\'](\w+)["\']\)',
            r'\$(\w+)_API_KEY',
            r'\$(\w+)_SECRET',
            r'\$(\w+)_URL',
            r'\$(\w+)_HOST',
            r'\$(\w+)_PORT',
            r'\$\{(\w+)\}',
        ]

        exts = (".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".env*")
        for f in self.project_path.rglob("*"):
            if f.is_dir() and f.name in ("node_modules", ".git", "venv", "__pycache__", "dist", "build", ".next"):
                continue
            if f.suffix not in exts and f.name not in (".env.example", ".env.sample"):
                continue
            if f.stat().st_size > 100000:
                continue
            try:
                content = f.read_text(errors="replace")
                for pat in patterns:
                    for m in re.finditer(pat, content, re.IGNORECASE):
                        env_vars.add(m.group(1))
            except Exception:
                continue

        return sorted(env_vars)

    def scan_existing_env(self) -> dict[str, str]:
        env_file = self.project_path / ".env"
        if env_file.exists():
            return self._parse_env_file(env_file)
        return {}

    def resolve(self, var_name: str, env_example: dict | None = None,
                sources: dict | None = None) -> str:
        if var_name in os.environ:
            self.categories[var_name] = "already_set"
            return os.environ[var_name]

        existing = self.scan_existing_env()
        if var_name in existing:
            self.categories[var_name] = "from_env_file"
            return existing[var_name]

        svc_name = service_name_from_env(var_name)
        if svc_name and self.service_manager:
            entry = self.service_manager.running.get(svc_name)
            if entry:
                url = self.service_manager._make_url(
                    entry["defs"],
                    port=entry.get("port", entry["defs"]["port"])
                )
                self.categories[var_name] = f"from_service_{svc_name}"
                return url

        if is_critical(var_name):
            self.categories[var_name] = "critical"
            return None

        if env_example and var_name in env_example:
            val = env_example[var_name]
            if val and val != var_name.lower():
                self.categories[var_name] = "from_example"
                return val

        self.categories[var_name] = "random"
        return self._random_value(var_name)

    def resolve_all(self, var_names: list[str] | None = None,
                    ask_user_callback=None) -> dict[str, str]:
        env_example = self.scan_env_example()
        result = {}

        to_resolve = var_names or list(env_example.keys())

        for var in to_resolve:
            val = self.resolve(var, env_example)
            if val is None:
                if ask_user_callback:
                    user_val = ask_user_callback(var)
                    if user_val:
                        result[var] = user_val
                        self.categories[var] = "user_provided"
                        continue
                val = self._random_value(var)
                self.categories[var] = "random_fallback"
            result[var] = val

        self.env = result
        return result

    def generate_env_file(self, env_vars: dict[str, str]) -> str:
        env_path = self.project_path / ".env"
        lines = []
        for key, val in env_vars.items():
            lines.append(f"{key}={val}")
        env_path.write_text("\n".join(lines) + "\n")
        return str(env_path)

    def update_env_file(self, updates: dict[str, str]) -> str:
        env_path = self.project_path / ".env"
        existing = {}
        if env_path.exists():
            existing = self._parse_env_file(env_path)

        existing.update(updates)
        lines = [f"{k}={v}" for k, v in existing.items()]
        env_path.write_text("\n".join(lines) + "\n")
        return str(env_path)

    def _random_value(self, var_name: str) -> str:
        if any(k in var_name.lower() for k in ("host", "hostname")):
            return "localhost"
        if any(k in var_name.lower() for k in ("port",)):
            return str(random.randint(3000, 9000))
        if any(k in var_name.lower() for k in ("url", "uri", "endpoint")):
            return f"http://localhost:{random.randint(3000, 9000)}"
        if any(k in var_name.lower() for k in ("email",)):
            return f"user@example.com"
        if any(k in var_name.lower() for k in ("path", "dir")):
            return f"/tmp/runit_{random_string(8)}"
        if any(k in var_name.lower() for k in ("debug", "verbose", "log_level")):
            return "true" if random.choice([True, False]) else "false"
        if any(k in var_name.lower() for k in ("password", "secret")):
            return random_string(24)
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=16))

    def _parse_env_file(self, path: Path) -> dict[str, str]:
        result = {}
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip().strip("\"'")
        except Exception:
            pass
        return result


def random_string(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))
