from sqlalchemy import create_engine
"""
SQLAlchemy database setup for the June agent.

This module initializes the database engine, session factory, and provides utilities
for table creation and session management. It's configured to use SQLite by default,
relative to the execution directory of the application.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os

# Import Base from ORM models, used for table creation.
from june_agent.models_v2.orm_models import Base

# Determine the database URL from environment variable or use a default.
# Defaulting to a local SQLite file named 'june_agent.db' in the current working directory.
# The './' prefix ensures it's relative to where the application is run.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./june_agent.db")

# Initialize the SQLAlchemy engine.
# `connect_args={"check_same_thread": False}` is specific to SQLite and allows the
# connection to be shared across threads, which is necessary for multithreaded
# applications like those using Flask's default development server or background threads.
#
# Foreign Key Support (PRAGMA foreign_keys=ON for SQLite):
# SQLAlchemy's SQLite dialect typically enables foreign key constraints by default
# on new connections if the SQLite version supports it. If issues with foreign key
# enforcement arise, an event listener can be used to explicitly set this pragma
# on each new connection (see commented-out example below).
#
# from sqlalchemy import event
# from sqlalchemy.engine import Engine
# Example event listener for SQLite PRAGMA:
# from sqlalchemy import event
# from sqlalchemy.engine import Engine
# @event.listens_for(Engine, "connect")
# def set_sqlite_pragma(dbapi_connection, connection_record):
#     """Ensures PRAGMA foreign_keys=ON is set for each SQLite connection."""
#     cursor = dbapi_connection.cursor()
#     cursor.execute("PRAGMA foreign_keys=ON")
#     cursor.close()

engine = create_engine(
    DATABASE_URL,
    # echo=True,  # Uncomment for debugging: logs all SQL statements.
    connect_args={"check_same_thread": False}
)

# Create a configured "SessionLocal" class.
# This factory will be used to create new database session instances.
# - autocommit=False: Transactions are not committed automatically. Explicit commit() is required.
# - autoflush=False: Session does not automatically flush changes to the DB before queries.
#   Flushing happens on commit or can be done manually with session.flush().
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_db_and_tables():
    """
    Creates all database tables defined by SQLAlchemy models that inherit from `Base`.

    This function should typically be called once at application startup to ensure
    the database schema is in place. It uses `Base.metadata.create_all(engine)`.
    If tables already exist, this operation does not modify them.
    """
    try:
        # For development, you might want to drop all tables first:
        # Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        # Using print for simple startup feedback; consider logging for production.
        print(f"Database tables checked/created successfully at {DATABASE_URL}.")
    except Exception as e:
        print(f"Error creating database tables at {DATABASE_URL}: {e}")
        # Re-raise the exception to ensure startup issues are not silently ignored.
        raise

def get_db() -> Session: # Specify return type for clarity
    """
    Provides a database session dependency.

    This generator function creates a new SQLAlchemy session for each call
    and ensures that the session is closed after its use, typically within
    a try/finally block in the calling code (e.g., a web request handler).

    Yields:
        sqlalchemy.orm.Session: The database session.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Example usage (typically for direct script execution or testing this module):
# if __name__ == "__main__":
#     print(f"Using database at: {DATABASE_URL}")
#     create_db_and_tables() # Create tables if they don't exist
#     print("Database setup complete.")
