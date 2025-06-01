import sqlite3
import logging
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

class DatabaseManager:
    def __init__(self, db_path='june_agent.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row # Access columns by name
            self.conn.execute("PRAGMA foreign_keys = ON;") # Enable foreign key support
            self.cursor = self.conn.cursor()
            logging.info(f"Successfully connected to SQLite database at {self.db_path} with foreign keys ON.")
        except sqlite3.Error as e:
            logging.error(f"Error connecting to SQLite database: {e}", exc_info=True)
            raise

    def close(self):
        if self.conn:
            self.conn.close()
            logging.info("SQLite database connection closed.")

    def execute_query(self, query, params=None):
        if not self.conn or not self.cursor:
            self.connect()
        try:
            self.cursor.execute(query, params or ())
            self.conn.commit()
            return self.cursor
        except sqlite3.Error as e:
            logging.error(f"Error executing query: {query} with params: {params}. Error: {e}", exc_info=True)
            # Optionally re-raise or handle more gracefully
            raise

    def fetch_one(self, query, params=None):
        if not self.conn or not self.cursor:
            self.connect()
        try:
            self.cursor.execute(query, params or ())
            return self.cursor.fetchone()
        except sqlite3.Error as e:
            logging.error(f"Error fetching one: {query} with params: {params}. Error: {e}", exc_info=True)
            raise

    def fetch_all(self, query, params=None):
        if not self.conn or not self.cursor:
            self.connect()
        try:
            self.cursor.execute(query, params or ())
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            logging.error(f"Error fetching all: {query} with params: {params}. Error: {e}", exc_info=True)
            raise

    def create_tables(self):
        if not self.conn or not self.cursor:
            self.connect()

        initiatives_table_sql = """
        CREATE TABLE IF NOT EXISTS initiatives (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """

        tasks_table_sql = """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            initiative_id TEXT,
            parent_task_id TEXT,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            phase TEXT,
            result TEXT,
            error_message TEXT, -- Added
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (initiative_id) REFERENCES initiatives (id) ON DELETE CASCADE,
            FOREIGN KEY (parent_task_id) REFERENCES tasks (id) ON DELETE CASCADE
        );
        """
        try:
            self.cursor.execute(initiatives_table_sql)
            logging.info("Successfully ensured 'initiatives' table exists.")
            self.cursor.execute(tasks_table_sql)
            logging.info("Successfully ensured 'tasks' table exists.")
            self.conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Error creating tables: {e}", exc_info=True)
            raise
        finally:
            # It's good practice to ensure connection is managed,
            # but for a setup script, might close explicitly after all setup.
            # For now, leave connection open if methods are called sequentially.
            pass

    def get_current_timestamp(self):
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

# Example usage (optional, for testing purposes within this file)
if __name__ == '__main__':
    db_manager = DatabaseManager(db_path='test_june_agent.db') # Use a test DB
    try:
        db_manager.connect()
        db_manager.create_tables()
        logging.info("Database tables created successfully for testing.")

        # Example: Add a test initiative
        # current_time = db_manager.get_current_timestamp()
        # try:
        #     db_manager.execute_query(
        #         "INSERT INTO initiatives (id, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        #         ('init_test_123', 'Test Initiative', 'A description for testing', 'active', current_time, current_time)
        #     )
        #     logging.info("Test initiative inserted.")
        #     retrieved_initiative = db_manager.fetch_one("SELECT * FROM initiatives WHERE id = ?", ('init_test_123',))
        #     if retrieved_initiative:
        #         logging.info(f"Retrieved test initiative: {dict(retrieved_initiative)}")
        #     else:
        #         logging.warning("Failed to retrieve test initiative.")
        # except sqlite3.IntegrityError as e:
        #     logging.warning(f"Test initiative already exists or other integrity error: {e}")


    except Exception as e:
        logging.error(f"An error occurred during __main__ test: {e}", exc_info=True)
    finally:
        db_manager.close()
        # os.remove('test_june_agent.db') # Clean up test DB
        # logging.info("Test database cleaned up.")
