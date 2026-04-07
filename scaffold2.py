import os

# Alembic setup
alembic_ini = """[alembic]
script_location = db/migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = postgresql+asyncpg://sk_app:localdev123@localhost:6432/sahulatkar

[post_write_hooks]
[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

env_py = """import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from sk_shared.models.base import Base
import os

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url")))

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

run_migrations_online()
"""

# Terraform setup
tf_main = """provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source = "../../modules/vpc"
}

module "rds" {
  source = "../../modules/rds"
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
}

module "eks" {
  source = "../../modules/eks"
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
}
"""

tf_vars = """variable "aws_region" {
  default = "me-central-1"
}
"""

with open('db/migrations/alembic.ini', 'w') as f:
    f.write(alembic_ini)

with open('db/migrations/env.py', 'w') as f:
    f.write(env_py)

for env in ['staging', 'production']:
    path = os.path.join('infra', 'terraform', 'environments', env)
    with open(os.path.join(path, 'main.tf'), 'w') as f:
        f.write(tf_main)
    with open(os.path.join(path, 'variables.tf'), 'w') as f:
        f.write(tf_vars)

print("Scaffolded DB & Terraform")
