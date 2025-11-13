"""PostgreSQL connection pooling for Gateway service."""
import os
import logging
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional
from prometheus_client import Gauge, Counter

logger = logging.getLogger(__name__)

# Prometheus metrics for connection pool
POOL_SIZE = Gauge(
    'gateway_db_pool_size',
    'Current PostgreSQL connection pool size',
    ['pool_name']
)
POOL_ACTIVE = Gauge(
    'gateway_db_pool_active_connections',
    'Active connections in PostgreSQL pool',
    ['pool_name']
)
POOL_IDLE = Gauge(
    'gateway_db_pool_idle_connections',
    'Idle connections in PostgreSQL pool',
    ['pool_name']
)
POOL_WAIT_TIME = Counter(
    'gateway_db_pool_wait_seconds_total',
    'Total time waiting for connections from pool',
    ['pool_name']
)
POOL_ERRORS = Counter(
    'gateway_db_pool_errors_total',
    'Total connection pool errors',
    ['pool_name', 'error_type']
)


class DatabaseConnectionPool:
    """Manages PostgreSQL connection pool for Gateway service."""
    
    def __init__(
        self,
        minconn: int = 2,
        maxconn: int = 20,
        pool_name: str = "default"
    ):
        """Initialize connection pool.
        
        Args:
            minconn: Minimum number of connections in pool
            maxconn: Maximum number of connections in pool
            pool_name: Name of the pool for metrics
        """
        self.pool_name = pool_name
        self.minconn = minconn
        self.maxconn = maxconn
        
        # Get database connection parameters
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "conversations")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "")
        
        # Build connection string
        conn_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
        if db_password:
            conn_string += f" password={db_password}"
        
        # Create connection pool
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                dsn=conn_string
            )
            logger.info(
                f"Created PostgreSQL connection pool '{pool_name}' "
                f"(min={minconn}, max={maxconn})"
            )
            
            # Update metrics
            POOL_SIZE.labels(pool_name=pool_name).set(maxconn)
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}", exc_info=True)
            POOL_ERRORS.labels(pool_name=pool_name, error_type="creation").inc()
            raise
    
    @contextmanager
    def get_connection(self, cursor_factory=None):
        """Get a connection from the pool.
        
        Args:
            cursor_factory: Optional cursor factory (e.g., RealDictCursor).
                          Note: This is stored for use when creating cursors,
                          but cursors should be created with: conn.cursor(cursor_factory=...)
            
        Yields:
            Database connection with cursor_factory attribute set if provided
        """
        import time
        start_time = time.time()
        
        conn = None
        try:
            # Get connection from pool
            conn = self.pool.getconn()
            if conn is None:
                POOL_ERRORS.labels(
                    pool_name=self.pool_name,
                    error_type="getconn_failed"
                ).inc()
                raise RuntimeError("Failed to get connection from pool")
            
            # Update metrics
            wait_time = time.time() - start_time
            POOL_WAIT_TIME.labels(pool_name=self.pool_name).inc(wait_time)
            
            # Store cursor factory as attribute for convenience
            # Users can still override by passing to cursor() directly
            if cursor_factory:
                conn._default_cursor_factory = cursor_factory
            
            # Update active/idle metrics
            self._update_pool_metrics()
            
            yield conn
            
        except psycopg2.Error as e:
            POOL_ERRORS.labels(
                pool_name=self.pool_name,
                error_type=type(e).__name__
            ).inc()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        except Exception as e:
            POOL_ERRORS.labels(
                pool_name=self.pool_name,
                error_type=type(e).__name__
            ).inc()
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise
        finally:
            # Return connection to pool
            if conn:
                try:
                    self.pool.putconn(conn)
                    self._update_pool_metrics()
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}")
                    POOL_ERRORS.labels(
                        pool_name=self.pool_name,
                        error_type="putconn_failed"
                    ).inc()
    
    def _update_pool_metrics(self):
        """Update Prometheus metrics for pool state."""
        try:
            # Get pool stats (approximate)
            # Note: psycopg2.pool doesn't expose exact stats, so we estimate
            # based on pool configuration
            POOL_ACTIVE.labels(pool_name=self.pool_name).set(
                self.pool._used  # Internal attribute, approximate
            )
            POOL_IDLE.labels(pool_name=self.pool_name).set(
                max(0, self.maxconn - self.pool._used)  # Approximate
            )
        except Exception as e:
            logger.debug(f"Could not update pool metrics: {e}")
    
    def closeall(self):
        """Close all connections in the pool."""
        try:
            self.pool.closeall()
            logger.info(f"Closed all connections in pool '{self.pool_name}'")
        except Exception as e:
            logger.error(f"Error closing pool: {e}", exc_info=True)


# Global connection pool instance
_db_pool: Optional[DatabaseConnectionPool] = None


def get_db_pool() -> DatabaseConnectionPool:
    """Get global database connection pool instance."""
    global _db_pool
    if _db_pool is None:
        minconn = int(os.getenv("POSTGRES_POOL_MIN", "2"))
        maxconn = int(os.getenv("POSTGRES_POOL_MAX", "20"))
        _db_pool = DatabaseConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            pool_name="gateway"
        )
    return _db_pool


def get_db_connection():
    """Get a database connection from the pool (backward compatibility).
    
    DEPRECATED: Use get_db_pool().get_connection() instead.
    """
    pool = get_db_pool()
    return pool.get_connection()


def close_db_pool():
    """Close the global database connection pool."""
    global _db_pool
    if _db_pool is not None:
        _db_pool.closeall()
        _db_pool = None
