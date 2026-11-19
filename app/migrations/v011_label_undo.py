"""Retain undone label versions for audit without using them in training."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upgrade(connection: AsyncConnection) -> None:
    columns = await connection.run_sync(lambda sync: {c['name'] for c in inspect(sync).get_columns('labels')})
    if 'undone_at' not in columns:
        column_type = 'TIMESTAMP WITH TIME ZONE' if connection.dialect.name == 'postgresql' else 'TIMESTAMP'
        await connection.execute(text(f'ALTER TABLE labels ADD COLUMN undone_at {column_type}'))
