import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from contextlib import contextmanager

load_dotenv()

# Create connection pool
# min_size: minimum connections kept alive
# max_size: maximum connections that can be created
# timeout: time to wait for connection before raising error
pool = ConnectionPool(
    conninfo=(
        f"host={os.getenv('DB_HOST')} "
        f"dbname={os.getenv('DB_NAME')} "
        f"user={os.getenv('DB_USER')} "
        f"password={os.getenv('DB_PASSWORD')} "
        f"port={os.getenv('DB_PORT')}"
    ),
    min_size=2,      # Keep 2 connections always ready
    max_size=10,     # Maximum 10 concurrent connections
    timeout=30,      # Wait up to 30s for connection
    open=True        # Open pool immediately
)

print(f"✅ Database connection pool created (min=2, max=10)")


@contextmanager
def get_connection():
    """
    Get a connection from the pool.

    Usage with context manager (recommended):
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ...")
            conn.commit()

    The connection is automatically returned to the pool when exiting context.
    """
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# Legacy support: conn object for existing code
# This maintains backward compatibility with existing non-context-manager code
class LegacyConnectionWrapper:
    """
    Wrapper to maintain backward compatibility with existing code.

    Gets a connection from pool for each operation.
    Properly returns connection after commit/rollback.

    WARNING: Less efficient than context managers.
    Migrate to get_connection() context manager for new code.
    """

    def __init__(self):
        self._current_conn = None

    def cursor(self, *args, **kwargs):
        # Get fresh connection from pool if we don't have one
        if self._current_conn is None:
            self._current_conn = pool.getconn()
        return self._current_conn.cursor(*args, **kwargs)

    def commit(self):
        if self._current_conn:
            try:
                self._current_conn.commit()
            finally:
                # Return connection to pool
                pool.putconn(self._current_conn)
                self._current_conn = None

    def rollback(self):
        if self._current_conn:
            try:
                self._current_conn.rollback()
            finally:
                # Return connection to pool
                pool.putconn(self._current_conn)
                self._current_conn = None

    def close(self):
        # Return connection to pool if we have one
        if self._current_conn:
            pool.putconn(self._current_conn)
            self._current_conn = None

    def __getattr__(self, name):
        # Forward any other attributes to current connection
        if self._current_conn:
            return getattr(self._current_conn, name)
        # Get a connection if we don't have one
        self._current_conn = pool.getconn()
        return getattr(self._current_conn, name)


# Maintain backward compatibility
conn = LegacyConnectionWrapper()

print("✅ Connected to PostgreSQL successfully!")
