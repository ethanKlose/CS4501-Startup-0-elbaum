from alembic import context
from sqlalchemy import engine_from_config, pool
from app.db import Base
from app import models


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


supplied = context.config.attributes.get('connection')
if supplied is not None:
    run(supplied)
elif context.is_offline_mode():
    context.configure(url=context.config.get_main_option('sqlalchemy.url'), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    from app.config import settings
    context.config.set_main_option('sqlalchemy.url', settings.database_url.replace('%', '%%'))
    engine = engine_from_config(context.config.get_section(context.config.config_ini_section), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as connection:
        run(connection)
