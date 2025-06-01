import unittest
import os
import sqlite3
from june_agent.db import DatabaseManager

TEST_DB_PATH = 'test_june_agent_db_unittest.db'

class TestDatabaseManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure no old test DB is lying around
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def setUp(self):
        # Each test gets a fresh DB manager and connection
        self.db_manager = DatabaseManager(db_path=TEST_DB_PATH)
        self.db_manager.connect()
        # Ensure tables are created for each test, connect() doesn't auto-create
        self.db_manager.create_tables()

    def tearDown(self):
        self.db_manager.close()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_connection(self):
        self.assertIsNotNone(self.db_manager.conn)
        self.assertIsNotNone(self.db_manager.cursor)
        # Check if connection is actually open by trying a simple query
        try:
            self.db_manager.cursor.execute("SELECT 1")
            result = self.db_manager.cursor.fetchone()
            self.assertEqual(result[0], 1)
        except sqlite3.Error as e:
            self.fail(f"Database connection check failed: {e}")

    def test_create_tables_idempotency(self):
        # Call create_tables again, should not fail
        try:
            self.db_manager.create_tables()
        except Exception as e:
            self.fail(f"create_tables failed on second call: {e}")

        # Verify tables exist by querying sqlite_master
        tables_query = "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('initiatives', 'tasks');"
        self.db_manager.cursor.execute(tables_query)
        tables = self.db_manager.cursor.fetchall()
        self.assertEqual(len(tables), 2, "Should find both 'initiatives' and 'tasks' tables.")
        table_names = sorted([table[0] for table in tables])
        self.assertListEqual(table_names, ['initiatives', 'tasks'])

    def test_execute_query_insert_select(self):
        # Test INSERT
        timestamp = self.db_manager.get_current_timestamp()
        insert_query = "INSERT INTO initiatives (id, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
        params = ('test_init_01', 'Test Initiative', 'A description', 'pending', timestamp, timestamp)
        try:
            self.db_manager.execute_query(insert_query, params)
        except Exception as e:
            self.fail(f"execute_query INSERT failed: {e}")

        # Test SELECT (fetch_one)
        select_query = "SELECT * FROM initiatives WHERE id = ?"
        row = self.db_manager.fetch_one(select_query, ('test_init_01',))
        self.assertIsNotNone(row)
        self.assertEqual(row['id'], 'test_init_01')
        self.assertEqual(row['name'], 'Test Initiative')

    def test_fetch_all(self):
        timestamp = self.db_manager.get_current_timestamp()
        initiatives_data = [
            ('init_01', 'Initiative 1', 'Desc 1', 'pending', timestamp, timestamp),
            ('init_02', 'Initiative 2', 'Desc 2', 'active', timestamp, timestamp),
        ]
        insert_query = "INSERT INTO initiatives (id, name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
        for data in initiatives_data:
            self.db_manager.execute_query(insert_query, data)

        rows = self.db_manager.fetch_all("SELECT * FROM initiatives ORDER BY name ASC")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['name'], 'Initiative 1')
        self.assertEqual(rows[1]['name'], 'Initiative 2')

    def test_fetch_one_not_found(self):
        row = self.db_manager.fetch_one("SELECT * FROM initiatives WHERE id = ?", ('non_existent_id',))
        self.assertIsNone(row)

    def test_foreign_key_cascade_delete_task(self):
        # This tests if deleting an initiative cascades to its tasks (defined in schema)
        # 1. Create an initiative
        ts = self.db_manager.get_current_timestamp()
        init_id = "fk_test_init"
        self.db_manager.execute_query(
            "INSERT INTO initiatives (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (init_id, "FK Test Init", ts, ts)
        )
        # 2. Create a task linked to this initiative
        task_id = "fk_test_task"
        self.db_manager.execute_query(
            "INSERT INTO tasks (id, initiative_id, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, init_id, "FK Test Task", ts, ts)
        )
        # Verify task exists
        task_row = self.db_manager.fetch_one("SELECT id FROM tasks WHERE id = ?", (task_id,))
        self.assertIsNotNone(task_row)

        # 3. Delete the initiative
        self.db_manager.execute_query("DELETE FROM initiatives WHERE id = ?", (init_id,))

        # 4. Verify the task is also deleted (due to ON DELETE CASCADE)
        # Need to enable foreign keys for SQLite connection if not by default for the session
        # self.db_manager.execute_query("PRAGMA foreign_keys = ON;") # Usually done per connection
        # The Python sqlite3 module typically has FKs off by default per connection.
        # Let's re-connect to ensure PRAGMA applies if needed, or test if default connection has it.
        # If this test fails, it might be because foreign_keys PRAGMA isn't active.
        # The schema `FOREIGN KEY (initiative_id) REFERENCES initiatives (id) ON DELETE CASCADE` is correct.
        # Python's sqlite3 connections need `conn.execute("PRAGMA foreign_keys = ON")` after connecting.
        # Add this to DatabaseManager.connect()

        # Re-fetch task to check if it's deleted
        task_row_after_delete = self.db_manager.fetch_one("SELECT id FROM tasks WHERE id = ?", (task_id,))
        self.assertIsNone(task_row_after_delete, "Task should be deleted by cascade when initiative is deleted.")

if __name__ == '__main__':
    unittest.main()
