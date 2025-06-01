import uuid
import logging
from june_agent.db import DatabaseManager # Assuming db.py is in june_agent package
# from june_agent.task import Task # Forward declaration for type hinting if needed early

logger = logging.getLogger(__name__)

class Initiative:
    def __init__(self, name: str, description: str, db_manager: DatabaseManager, initiative_id: str | None = None, status: str = 'pending', created_at: str | None = None, updated_at: str | None = None):
        self.id = initiative_id if initiative_id else uuid.uuid4().hex
        self.name = name
        self.description = description
        self.db_manager = db_manager
        self.status = status
        self.tasks = [] # In-memory list of Task objects associated with this initiative

        current_time = self.db_manager.get_current_timestamp()
        self.created_at = created_at if created_at else current_time
        self.updated_at = updated_at if updated_at else current_time

        logger.info(f"Initiative initialized: {self.name} (ID: {self.id})")

    def add_task_object(self, task) -> None: # Changed method name to avoid conflict
        """Adds an existing Task object to this initiative's in-memory list."""
        if task not in self.tasks:
            self.tasks.append(task)
            task.initiative_id = self.id # Ensure task knows its initiative
            logger.info(f"Task {task.id} added to initiative {self.id} in memory.")
        else:
            logger.warning(f"Task {task.id} already present in initiative {self.id}.")


    def update_status(self, new_status: str) -> None:
        self.status = new_status
        self.updated_at = self.db_manager.get_current_timestamp()
        logger.info(f"Initiative {self.id} status updated to {new_status}.")
        self.save() # Persist status change

    def save(self) -> None:
        """Saves the initiative to the database."""
        query_select = "SELECT id FROM initiatives WHERE id = ?"
        existing = self.db_manager.fetch_one(query_select, (self.id,))

        self.updated_at = self.db_manager.get_current_timestamp() # Ensure updated_at is fresh

        if existing:
            query_update = """
            UPDATE initiatives
            SET name = ?, description = ?, status = ?, updated_at = ?
            WHERE id = ?
            """
            try:
                self.db_manager.execute_query(query_update, (self.name, self.description, self.status, self.updated_at, self.id))
                logger.info(f"Initiative {self.id} updated in the database.")
            except Exception as e:
                logger.error(f"Failed to update initiative {self.id}: {e}", exc_info=True)
        else:
            query_insert = """
            INSERT INTO initiatives (id, name, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            try:
                self.db_manager.execute_query(query_insert, (self.id, self.name, self.description, self.status, self.created_at, self.updated_at))
                logger.info(f"Initiative {self.id} saved to the database.")
            except Exception as e:
                logger.error(f"Failed to save new initiative {self.id}: {e}", exc_info=True)

    @classmethod
    def load(cls, initiative_id: str, db_manager: DatabaseManager):
        """Loads an initiative from the database by its ID."""
        query = "SELECT id, name, description, status, created_at, updated_at FROM initiatives WHERE id = ?"
        row = db_manager.fetch_one(query, (initiative_id,))
        if row:
            logger.info(f"Initiative {initiative_id} loaded from database.")
            # tasks will need to be loaded separately if desired upon loading an initiative
            return cls(name=row['name'], description=row['description'], db_manager=db_manager,
                       initiative_id=row['id'], status=row['status'], created_at=row['created_at'], updated_at=row['updated_at'])
        else:
            logger.warning(f"Initiative with ID {initiative_id} not found in the database.")
            return None

    def to_dict(self) -> dict:
        """Returns a dictionary representation of the initiative."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'num_tasks': len(self.tasks), # Number of in-memory tasks
            'task_ids': [task.id for task in self.tasks] # IDs of in-memory tasks
        }

    @classmethod
    def load_all(cls, db_manager: DatabaseManager):
        """Loads all initiatives from the database."""
        query = "SELECT id FROM initiatives ORDER BY created_at DESC"
        rows = db_manager.fetch_all(query)
        initiatives = []
        for row in rows:
            initiative = cls.load(row['id'], db_manager)
            if initiative:
                initiatives.append(initiative)
        logger.info(f"Loaded {len(initiatives)} initiatives from database.")
        return initiatives

if __name__ == '__main__':
    # This is a basic test block. More comprehensive tests should be in the tests/ directory.
    logger.info("Running basic test for Initiative class...")
    # Use a dedicated test DB or ensure cleanup
    db_path_test = 'test_initiative_june_agent.db'
    db_manager_test = DatabaseManager(db_path=db_path_test)

    try:
        db_manager_test.connect()
        db_manager_test.create_tables() # Ensure tables are created

        # Create and save a new initiative
        test_initiative_name = "Test Initiative Alpha"
        test_initiative_desc = "Description for test initiative Alpha."
        initiative_alpha = Initiative(name=test_initiative_name, description=test_initiative_desc, db_manager=db_manager_test)
        initiative_alpha.save()
        logger.info(f"Saved initiative: {initiative_alpha.to_dict()}")

        # Load the initiative from DB
        loaded_initiative = Initiative.load(initiative_id=initiative_alpha.id, db_manager=db_manager_test)
        if loaded_initiative:
            logger.info(f"Loaded initiative: {loaded_initiative.to_dict()}")
            assert loaded_initiative.name == test_initiative_name
            assert loaded_initiative.id == initiative_alpha.id
        else:
            logger.error("Failed to load initiative.")

        # Update status
        if loaded_initiative:
            loaded_initiative.update_status("in_progress")
            # Verify by loading again
            reloaded_initiative = Initiative.load(initiative_id=loaded_initiative.id, db_manager=db_manager_test)
            if reloaded_initiative:
                logger.info(f"Reloaded initiative after status update: {reloaded_initiative.to_dict()}")
                assert reloaded_initiative.status == "in_progress"
            else:
                logger.error("Failed to reload initiative after status update.")

    except Exception as e:
        logger.error(f"Error during Initiative class test: {e}", exc_info=True)
    finally:
        db_manager_test.close()
        # import os
        # os.remove(db_path_test) # Clean up the test database
        # logger.info(f"Test database {db_path_test} removed.")
