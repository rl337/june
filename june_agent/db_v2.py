from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session # Added Session for type hinting
import os

# Assuming orm_models.py is in june_agent.models_v2
from june_agent.models_v2.orm_models import Base

# Database URL: Use environment variable or default to a local SQLite file
# For consistency with previous setup, default to 'june_agent.db' in the project root.
# The actual path might need adjustment based on where the main script runs.
# For now, let's assume it's relative to where the agent starts.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./june_agent.db")

# Create the SQLAlchemy engine
# connect_args are specific to SQLite for enabling foreign key support if needed,
# though SQLAlchemy usually handles this. For SQLite, it's good practice.
# However, PRAGMA foreign_keys=ON is a per-connection setting for SQLite.
# SQLAlchemy's default SQLite dialect enables FKs by default on new connections if supported.
# If issues arise, one might need to use event listeners:
# from sqlalchemy import event
# from sqlalchemy.engine import Engine
# @event.listens_for(Engine, "connect")
# def set_sqlite_pragma(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("PRAGMA foreign_keys=ON")
#     cursor.close()
engine = create_engine(
    DATABASE_URL,
    # For SQLite, echo can be useful for debugging generated SQL
    # echo=True,
    connect_args={"check_same_thread": False} # Needed for SQLite when used with threads (like Flask dev server)
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_db_and_tables():
    """
    Creates all tables in the database defined by SQLAlchemy models
    that inherit from Base. This function should be called once at application startup.
    """
    try:
        # Base.metadata.drop_all(bind=engine) # Uncomment to drop tables first (for development)
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully (if they didn't exist).")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        raise

# Dependency to get a DB session (useful for web frameworks like FastAPI, can be adapted)
def get_db():
    """
    Provides a database session for a single request or operation.
    Ensures the session is closed after use.
    """
    db: Session = SessionLocal() # Add type hint for db
    try:
        yield db
    finally:
        db.close()

# Example of how to use:
# if __name__ == "__main__":
#     print(f"Database URL: {DATABASE_URL}")
#     create_db_and_tables()
#     print("Initialization complete. You can now use get_db() to get sessions.")

    # Example usage of a session:
    # db_session_gen = get_db()
    # my_db_session = next(db_session_gen)
    # try:
    #     # ... perform database operations with my_db_session ...
    #     # e.g., new_initiative = InitiativeORM(name="Test from main")
    #     # my_db_session.add(new_initiative)
    #     # my_db_session.commit()
    #     pass
    # finally:
    #     my_db_session.close() # Or rely on the finally block in get_db if used as a context manager
