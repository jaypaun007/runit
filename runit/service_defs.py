SERVICE_DEFS = {
    "postgresql": {
        "name": "PostgreSQL",
        "docker_image": "postgres:16-alpine",
        "docker_env": {"POSTGRES_PASSWORD": "app", "POSTGRES_DB": "app", "POSTGRES_USER": "app"},
        "apt_packages": ["postgresql", "postgresql-client"],
        "start_cmd": "pg_ctlcluster {version} main start 2>/dev/null || service postgresql start",
        "stop_cmd": "pg_ctlcluster {version} main stop 2>/dev/null || service postgresql stop",
        "configure_cmds": [
            'for f in /etc/postgresql/*/main/pg_hba.conf; do '
            '[ -f "$f" ] && echo "local all all trust" > "$f" && '
            'echo "host all all 127.0.0.1/32 trust" >> "$f" && '
            'echo "host all all ::1/128 trust" >> "$f"; '
            'done; '
            '(pg_ctlcluster 16 main reload 2>/dev/null) || '
            '(pg_ctlcluster 15 main reload 2>/dev/null) || '
            '(pg_ctlcluster 14 main reload 2>/dev/null) || '
            '(service postgresql restart 2>/dev/null) || true; '
            'sleep 1; '
            'psql -h localhost -U postgres -c "CREATE USER app WITH PASSWORD \'app\'" 2>/dev/null || true; '
            'psql -h localhost -U postgres -c "CREATE DATABASE app OWNER app" 2>/dev/null || true; '
            'psql -h localhost -U app -d app -c "SELECT 1" 2>/dev/null && echo "PG_OK" || echo "PG_WARN"',
        ],
        "health_cmd": ["sh", "-c", "PGPASSWORD=app psql -h localhost -U app -d app -c 'SELECT 1' 2>/dev/null"],
        "port": 5432,
        "connection_url": "postgresql://app:app@{host}:{port}/app",
        "env_vars": ["DATABASE_URL", "POSTGRES_URL", "PGHOST", "PGPORT"],
    },
    "redis": {
        "name": "Redis",
        "docker_image": "redis:7-alpine",
        "docker_env": {},
        "apt_packages": ["redis-server"],
        "start_cmd": "redis-server --daemonize yes --port {port} --loglevel warning",
        "stop_cmd": "redis-cli -p {port} shutdown 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [],
        "binary_url": "http://download.redis.io/releases/redis-7.2.5.tar.gz",
        "health_cmd": ["redis-cli", "-p", "{port}", "PING"],
        "port": 6379,
        "connection_url": "redis://{host}:{port}/0",
        "env_vars": ["REDIS_URL", "REDIS_HOST", "REDIS_PORT"],
    },
    "mysql": {
        "name": "MySQL",
        "docker_image": "mysql:8.0",
        "docker_env": {"MYSQL_ROOT_PASSWORD": "root", "MYSQL_DATABASE": "app", "MYSQL_USER": "app", "MYSQL_PASSWORD": "app"},
        "apt_packages": ["mysql-server"],
        "start_cmd": "mysqld --daemonize --skip-grant-tables 2>/dev/null || service mysql start",
        "stop_cmd": "mysqladmin -u root shutdown 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [
            "mysql -u root -e \"CREATE USER IF NOT EXISTS 'app'@'localhost' IDENTIFIED BY 'app'\" 2>/dev/null || true",
            "mysql -u root -e \"CREATE DATABASE IF NOT EXISTS app CHARACTER SET utf8mb4\" 2>/dev/null || true",
            "mysql -u root -e \"GRANT ALL ON app.* TO 'app'@'localhost'\" 2>/dev/null || true",
        ],
        "binary_url": None,
        "health_cmd": ["mysqladmin", "ping", "-h", "localhost", "-u", "root"],
        "port": 3306,
        "connection_url": "mysql://app:app@{host}:{port}/app",
        "env_vars": ["DATABASE_URL", "MYSQL_URL", "MYSQL_HOST", "MYSQL_PORT"],
    },
    "mongodb": {
        "name": "MongoDB",
        "docker_image": "mongo:7",
        "docker_env": {"MONGO_INITDB_DATABASE": "app"},
        "apt_packages": ["mongodb-org"],
        "start_cmd": "mongod --fork --logpath /tmp/mongod.log --dbpath /tmp/mongodb 2>/dev/null || mongosh --eval 'db.runCommand({ping:1})'",
        "stop_cmd": "mongod --shutdown 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["mongosh", "--eval", "db.runCommand({ping:1})", "--quiet"],
        "port": 27017,
        "connection_url": "mongodb://{host}:{port}/app",
        "env_vars": ["MONGODB_URL", "MONGO_URL", "MONGODB_URI"],
    },
    "rabbitmq": {
        "name": "RabbitMQ",
        "docker_image": "rabbitmq:3-management-alpine",
        "docker_env": {"RABBITMQ_DEFAULT_USER": "app", "RABBITMQ_DEFAULT_PASS": "app", "RABBITMQ_DEFAULT_VHOST": "app"},
        "apt_packages": ["rabbitmq-server"],
        "start_cmd": "rabbitmq-server -detached 2>/dev/null || true",
        "stop_cmd": "rabbitmqctl stop 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [
            "rabbitmqctl add_user app app 2>/dev/null || true",
            "rabbitmqctl add_vhost app 2>/dev/null || true",
            "rabbitmqctl set_permissions -p app app '.*' '.*' '.*' 2>/dev/null || true",
        ],
        "binary_url": None,
        "health_cmd": ["rabbitmqctl", "status"],
        "port": 5672,
        "connection_url": "amqp://app:app@{host}:{port}/app",
        "env_vars": ["RABBITMQ_URL", "AMQP_URL", "RABBITMQ_HOST"],
    },
    "mariadb": {
        "name": "MariaDB",
        "docker_image": "mariadb:11",
        "docker_env": {"MARIADB_ROOT_PASSWORD": "root", "MARIADB_DATABASE": "app", "MARIADB_USER": "app", "MARIADB_PASSWORD": "app"},
        "apt_packages": ["mariadb-server"],
        "start_cmd": "mysqld --daemonize 2>/dev/null || service mariadb start",
        "stop_cmd": "mysqladmin -u root shutdown 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [
            "mysql -u root -e \"CREATE USER IF NOT EXISTS 'app'@'localhost' IDENTIFIED BY 'app'\" 2>/dev/null || true",
            "mysql -u root -e \"CREATE DATABASE IF NOT EXISTS app\" 2>/dev/null || true",
            "mysql -u root -e \"GRANT ALL ON app.* TO 'app'@'localhost'\" 2>/dev/null || true",
        ],
        "binary_url": None,
        "health_cmd": ["mysqladmin", "ping", "-h", "localhost", "-u", "root"],
        "port": 3306,
        "connection_url": "mysql://app:app@{host}:{port}/app",
        "env_vars": ["DATABASE_URL", "MARIADB_URL", "MARIADB_HOST"],
    },
    "nginx": {
        "name": "Nginx",
        "docker_image": "nginx:alpine",
        "docker_env": {},
        "apt_packages": ["nginx"],
        "start_cmd": "nginx 2>/dev/null || service nginx start",
        "stop_cmd": "nginx -s quit 2>/dev/null || service nginx stop",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["nginx", "-t"],
        "port": 80,
        "connection_url": "http://{host}:{port}",
        "env_vars": ["NGINX_HOST", "NGINX_PORT"],
    },
    "sqlite": {
        "name": "SQLite",
        "docker_image": "",
        "docker_env": {},
        "apt_packages": ["sqlite3"],
        "start_cmd": "",
        "stop_cmd": "",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["sqlite3", "--version"],
        "port": 0,
        "connection_url": "sqlite:///{project_path}/data.db",
        "env_vars": ["SQLITE_PATH", "DATABASE_PATH"],
    },
    "elasticsearch": {
        "name": "Elasticsearch",
        "docker_image": "elasticsearch:8.11.0",
        "docker_env": {"discovery.type": "single-node", "xpack.security.enabled": "false", "ES_JAVA_OPTS": "-Xms512m -Xmx512m"},
        "apt_packages": ["elasticsearch"],
        "start_cmd": "elasticsearch -d -p /tmp/es.pid 2>/dev/null || service elasticsearch start",
        "stop_cmd": "kill $(cat /tmp/es.pid 2>/dev/null) 2>/dev/null || kill $(lsof -ti:{port}) 2>/dev/null",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["curl", "-s", "http://localhost:{port}"],
        "port": 9200,
        "connection_url": "http://{host}:{port}",
        "env_vars": ["ELASTICSEARCH_URL", "ES_URL"],
    },
    "clickhouse": {
        "name": "ClickHouse",
        "docker_image": "clickhouse/clickhouse-server:latest",
        "docker_env": {},
        "apt_packages": ["clickhouse-server", "clickhouse-client"],
        "start_cmd": "service clickhouse-server start 2>/dev/null || clickhouse-server --daemon --pid-file /tmp/ch.pid",
        "stop_cmd": "kill $(cat /tmp/ch.pid 2>/dev/null) 2>/dev/null || service clickhouse-server stop",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["clickhouse-client", "--query", "SELECT 1"],
        "port": 8123,
        "connection_url": "http://{host}:{port}",
        "env_vars": ["CLICKHOUSE_URL", "CLICKHOUSE_HOST"],
    },
    "neo4j": {
        "name": "Neo4j",
        "docker_image": "neo4j:latest",
        "docker_env": {"NEO4J_AUTH": "neo4j/password"},
        "apt_packages": ["neo4j"],
        "start_cmd": "neo4j start 2>/dev/null || true",
        "stop_cmd": "neo4j stop 2>/dev/null || true",
        "configure_cmds": [],
        "binary_url": None,
        "health_cmd": ["curl", "-s", "http://localhost:7474"],
        "port": 7687,
        "connection_url": "bolt://neo4j:password@{host}:{port}",
        "env_vars": ["NEO4J_URI", "NEO4J_URL", "NEO4J_HOST"],
    },
}


SERVICE_URL_TEMPLATES = {
    "postgresql": {
        "DATABASE_URL": "postgresql://app:app@{host}:{port}/app",
        "POSTGRES_URL": "postgresql://app:app@{host}:{port}/app",
    },
    "redis": {
        "REDIS_URL": "redis://{host}:{port}/0",
    },
    "mysql": {
        "DATABASE_URL": "mysql://app:app@{host}:{port}/app",
        "MYSQL_URL": "mysql://app:app@{host}:{port}/app",
    },
    "mongodb": {
        "MONGODB_URL": "mongodb://{host}:{port}/app",
    },
    "rabbitmq": {
        "RABBITMQ_URL": "amqp://app:app@{host}:{port}/app",
    },
    "mariadb": {
        "DATABASE_URL": "mysql://app:app@{host}:{port}/app",
        "MARIADB_URL": "mysql://app:app@{host}:{port}/app",
    },
}


SERVICE_APT_MAP = {
    "postgresql": "postgresql postgresql-client",
    "postgres": "postgresql postgresql-client",
    "redis": "redis-server",
    "mysql": "mysql-server",
    "mongodb": "mongodb-org",
    "mongo": "mongodb-org",
    "rabbitmq": "rabbitmq-server",
    "nginx": "nginx",
    "sqlite": "sqlite3",
    "elasticsearch": "elasticsearch",
    "clickhouse": "clickhouse-server clickhouse-client",
    "neo4j": "neo4j",
    "cassandra": "cassandra",
}


SERVICE_NAMES = list(SERVICE_DEFS.keys())
