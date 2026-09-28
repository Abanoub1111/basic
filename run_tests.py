"""Load .env, prepare PostgreSQL, and run database tests (or all tests)."""
import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def create_test_database(url):
    """Connect to the maintenance database to create the test database once."""
    admin_url = url.set(database='postgres')
    engine = create_async_engine(admin_url, isolation_level='AUTOCOMMIT')
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text('SELECT 1 FROM pg_database WHERE datname = :name'),
                {'name': url.database},
            )
            if not exists:
                name = engine.dialect.identifier_preparer.quote_identifier(url.database)
                await connection.exec_driver_sql(f'CREATE DATABASE {name}')
                print(f'Created {url.database}.', flush=True)
            else:
                print(f'Using existing {url.database}.', flush=True)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true', help='Also run unit, integration, and live AI tests')
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    os.chdir(root)
    load_dotenv(root / '.env')
    raw_url = os.getenv('TEST_DATABASE_URL')
    if not raw_url:
        parser.error('Add TEST_DATABASE_URL to .env first.')
    try:
        url = make_url(raw_url)
    except Exception:
        parser.error('TEST_DATABASE_URL is not a valid database URL.')
    if url.drivername != 'postgresql+asyncpg':
        parser.error('TEST_DATABASE_URL must start with postgresql+asyncpg://')
    if not url.database or not url.database.endswith('_test'):
        parser.error('Use a separate database whose name ends in _test, such as email_assistant_test.')
    if args.all and not os.getenv('GROQ_API_KEY', '').strip():
        parser.error('Add GROQ_API_KEY to .env to run --all.')

    try:
        asyncio.run(create_test_database(url))
    except Exception as error:
        print(f'Database preparation failed ({type(error).__name__}).')
        print('Check TEST_DATABASE_URL, start PostgreSQL, and ensure the database user can create databases.')
        print('For the bundled server: docker compose up -d --wait postgres')
        return 1

    # Override only this process; the application setting in .env stays unchanged.
    previous_url = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = raw_url
    try:
        print('Applying test database migrations...', flush=True)
        command.upgrade(Config(str(root / 'alembic.ini')), 'head')
    finally:
        if previous_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = previous_url

    options = ['--run-database', '-v']
    options += ['--run-ai'] if args.all else ['-m', 'database']
    return pytest.main(options)


if __name__ == '__main__':
    raise SystemExit(main())
