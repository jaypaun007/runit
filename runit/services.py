import os
import subprocess
import time
import shutil
import re
from pathlib import Path

from runit.environment import has_docker
from runit.cli import _console


SERVICES = {
    "postgresql": {
        "name": "PostgreSQL",
        "docker_image": "postgres:16-alpine",
        "default_port": 5432,
        "env_vars": ["DATABASE_URL", "POSTGRES_URL", "PGHOST", "PGPORT"],
        "check_cmd": ["pg_isready", "-h", "localhost"],
        "native_cmd": ["pg_ctl", "start"],
    },
    "redis": {
        "name": "Redis",
        "docker_image": "redis:7-alpine",
        "default_port": 6379,
        "env_vars": ["REDIS_URL", "REDIS_HOST", "REDIS_PORT"],
        "check_cmd": ["redis-cli", "ping"],
        "native_cmd": ["redis-server", "--daemonize", "yes"],
    },
    "mysql": {
        "name": "MySQL",
        "docker_image": "mysql:8.0",
        "default_port": 3306,
        "env_vars": ["MYSQL_URL", "MYSQL_HOST", "MYSQL_PORT", "DATABASE_URL"],
        "check_cmd": ["mysqladmin", "ping", "-h", "localhost"],
        "native_cmd": ["mysqld", "--daemonize"],
    },
    "mongodb": {
        "name": "MongoDB",
        "docker_image": "mongo:7",
        "default_port": 27017,
        "env_vars": ["MONGODB_URL", "MONGO_URL", "MONGODB_URI"],
        "check_cmd": ["mongosh", "--eval", "db.runCommand({ping:1})"],
        "native_cmd": ["mongod", "--fork", "--logpath", "/var/log/mongodb.log"],
    },
    "rabbitmq": {
        "name": "RabbitMQ",
        "docker_image": "rabbitmq:3-management-alpine",
        "default_port": 5672,
        "env_vars": ["RABBITMQ_URL", "AMQP_URL", "RABBITMQ_HOST"],
        "check_cmd": ["rabbitmqctl", "status"],
        "native_cmd": ["rabbitmq-server", "-detached"],
    },
    "elasticsearch": {
        "name": "Elasticsearch",
        "docker_image": "elasticsearch:8.11.0",
        "default_port": 9200,
        "env_vars": ["ELASTICSEARCH_URL", "ES_URL", "ELASTICSEARCH_HOST"],
        "check_cmd": [],
        "native_cmd": [],
    },
    "mariadb": {
        "name": "MariaDB",
        "docker_image": "mariadb:11",
        "default_port": 3306,
        "env_vars": ["MARIADB_URL", "MARIADB_HOST", "DATABASE_URL"],
        "check_cmd": ["mysqladmin", "ping", "-h", "localhost"],
        "native_cmd": [],
    },
    "cassandra": {
        "name": "Cassandra",
        "docker_image": "cassandra:5",
        "default_port": 9042,
        "env_vars": ["CASSANDRA_URL", "CASSANDRA_HOST"],
        "check_cmd": [],
        "native_cmd": [],
    },
    "nginx": {
        "name": "Nginx",
        "docker_image": "nginx:alpine",
        "default_port": 80,
        "env_vars": ["NGINX_HOST", "NGINX_PORT"],
        "check_cmd": ["nginx", "-t"],
        "native_cmd": ["nginx"],
    },
    "sqlite": {
        "name": "SQLite",
        "docker_image": "",
        "default_port": 0,
        "env_vars": ["SQLITE_PATH", "DATABASE_PATH"],
        "check_cmd": [],
        "native_cmd": [],
    },
    "clickhouse": {
        "name": "ClickHouse",
        "docker_image": "clickhouse/clickhouse-server:latest",
        "default_port": 8123,
        "env_vars": ["CLICKHOUSE_URL", "CLICKHOUSE_HOST"],
        "check_cmd": [],
        "native_cmd": [],
    },
    "neo4j": {
        "name": "Neo4j",
        "docker_image": "neo4j:latest",
        "default_port": 7687,
        "env_vars": ["NEO4J_URL", "NEO4J_HOST", "NEO4J_URI"],
        "check_cmd": [],
        "native_cmd": [],
    },
    "minio": {
        "name": "MinIO",
        "docker_image": "minio/minio:latest",
        "default_port": 9000,
        "env_vars": ["MINIO_URL", "MINIO_ENDPOINT", "S3_ENDPOINT"],
        "check_cmd": [],
        "native_cmd": [],
    },
}


def _find_service_by_env_var(env_name: str) -> str | None:
    for key, svc in SERVICES.items():
        for var in svc["env_vars"]:
            lower_var = var.lower()
            lower_env = env_name.lower()
            if lower_var == lower_env or lower_var in lower_env or lower_env in lower_var:
                return key
    return None


def _find_service_by_port(port: int) -> str | None:
    for key, svc in SERVICES.items():
        if svc["default_port"] == port:
            return key
    return None


def detect_required_services(project_path: str, plan: dict | None = None) -> list[str]:
    detected = set()
    root = Path(project_path)

    docker_compose = root / "docker-compose.yml"
    if not docker_compose.exists():
        docker_compose = root / "docker-compose.yaml"

    if docker_compose.exists():
        content = docker_compose.read_text(encoding="utf-8", errors="replace")
        for key, svc in SERVICES.items():
            if key in content.lower() or svc["docker_image"].split(":")[0] in content.lower():
                detected.add(key)

    env_vars = plan.get("required_env", []) if plan else []
    for env in env_vars:
        match = _find_service_by_env_var(env)
        if match:
            detected.add(match)

    req_files = [
        root / "requirements.txt",
        root / "package.json",
    ]
    for rf in req_files:
        if rf.exists():
            content = rf.read_text(encoding="utf-8", errors="replace").lower()
            for key, svc in SERVICES.items():
                if key in content or svc["name"].lower() in content:
                    detected.add(key)

    return list(detected)


def _check_service_running(service_key: str) -> bool:
    svc = SERVICES.get(service_key)
    if not svc:
        return False

    check_cmd = svc["check_cmd"]
    if not check_cmd:
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", svc["default_port"]))
            sock.close()
            return result == 0
        except Exception:
            return False

    try:
        result = subprocess.run(
            check_cmd, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _start_via_docker(service_key: str) -> bool:
    svc = SERVICES.get(service_key)
    if not svc:
        return False

    name = f"runit_{service_key}"
    port = svc["default_port"]

    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True, timeout=15
    )

    env_flags = []
    if service_key == "postgresql":
        env_flags = ["-e", "POSTGRES_PASSWORD=postgres", "-e", "POSTGRES_DB=app"]
    elif service_key == "mysql":
        env_flags = ["-e", "MYSQL_ROOT_PASSWORD=root", "-e", "MYSQL_DATABASE=app"]
    elif service_key == "mariadb":
        env_flags = ["-e", "MARIADB_ROOT_PASSWORD=root", "-e", "MARIADB_DATABASE=app"]
    elif service_key == "mongodb":
        env_flags = ["-e", "MONGO_INITDB_DATABASE=app"]
    elif service_key == "elasticsearch":
        env_flags = ["-e", "discovery.type=single-node", "-e", "xpack.security.enabled=false"]

    cmd = [
        "docker", "run", "-d", "--rm",
        "--name", name,
        "-p", f"{port}:{port}",
    ] + env_flags + [svc["docker_image"]]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            time.sleep(3)
            if _check_service_running(service_key):
                return True
            time.sleep(5)
            return _check_service_running(service_key)
        return False
    except Exception:
        return False


def _start_native(service_key: str) -> bool:
    svc = SERVICES.get(service_key)
    if not svc:
        return False

    native_cmd = svc["native_cmd"]
    if not native_cmd or not shutil.which(native_cmd[0]):
        return False

    try:
        result = subprocess.run(native_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            time.sleep(2)
            return _check_service_running(service_key)
        return False
    except Exception:
        return False


def start_service(service_key: str) -> tuple[bool, str]:
    svc = SERVICES.get(service_key)
    if not svc:
        return False, f"Unknown service: {service_key}"

    if _check_service_running(service_key):
        return True, f"{svc['name']} already running on port {svc['default_port']}"

    if has_docker():
        ok = _start_via_docker(service_key)
        if ok:
            return True, f"{svc['name']} started via Docker on port {svc['default_port']}"

    ok = _start_native(service_key)
    if ok:
        return True, f"{svc['name']} started natively on port {svc['default_port']}"

    return False, f"Could not start {svc['name']} (try installing Docker or running it manually)"


def start_required_services(project_path: str, plan: dict | None = None) -> list[dict]:
    c = _console()
    required = detect_required_services(project_path, plan)
    results = []

    if not required:
        return results

    if c:
        c.print(f"\n  [bold cyan]\U0001f6e0  Required services detected: {', '.join(required)}[/]")

    for svc_key in required:
        if c:
            c.print(f"  [yellow]Starting {SERVICES[svc_key]['name']}...[/]")
        ok, msg = start_service(svc_key)
        results.append({"service": svc_key, "ok": ok, "message": msg})
        if c:
            icon = "\u2705" if ok else "\u274c"
            c.print(f"  {icon} {msg}")

    return results


def get_service_urls() -> dict:
    urls = {}
    for key, svc in SERVICES.items():
        if _check_service_running(key):
            urls[key] = f"localhost:{svc['default_port']}"
    return urls
