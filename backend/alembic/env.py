"""Alembic 环境配置：使用同步驱动 + 项目 Settings + 全部 ORM 元数据。

迁移用同步 PyMySQL 驱动（mysql+pymysql），避免引入额外异步胶水；
应用运行时仍是 asyncmy 异步驱动，互不影响。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_database_url() -> str:
    """把异步 URL (mysql+asyncmy) 切换为同步 URL (mysql+pymysql)。"""
    url = settings.database_url
    return url.replace("mysql+asyncmy", "mysql+pymysql", 1)


config.set_main_option("sqlalchemy.url", _sync_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
