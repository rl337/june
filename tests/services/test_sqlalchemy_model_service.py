import unittest
import os
import datetime

from june_agent.services.sqlalchemy_model_service import SQLAlchemyModelService
from june_agent.db_v2 import SessionLocal, create_db_and_tables, engine, Base
from june_agent.models_v2.pydantic_models import (
    InitiativeCreate, InitiativeUpdate,
    TaskCreate, TaskUpdate
)
from june_agent.task import Task as DomainTask # For status/phase constants

TEST_DB_PATH_SVC = 'test_june_agent_service_sqlalchemy.db'
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH_SVC}"

# Need to import create_engine and sessionmaker for the test class setup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class TestSQLAlchemyModelService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Override the main engine and SessionLocal for testing
        # This is tricky if db_v2.engine is imported directly by other modules at import time.
        # A better way is to have db_v2.py use a configurable DATABASE_URL.
        # For now, we'll recreate tables in a specific test DB.
        # Ensure the engine used by the service is for the test DB.
        # The SQLAlchemyModelService takes a session_factory. We can give it one for the test DB.

        if os.path.exists(TEST_DB_PATH_SVC):
            os.remove(TEST_DB_PATH_SVC)

        # Create a new engine and session factory for the test database
        cls.test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
        cls.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.test_engine)

        # Create tables in the test database
        Base.metadata.create_all(bind=cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH_SVC):
            os.remove(TEST_DB_PATH_SVC)

    def setUp(self):
        # Each test gets a fresh service instance with the test session factory
        self.model_service = SQLAlchemyModelService(session_factory=self.TestSessionLocal)

        # Clean tables before each test
        # This is one strategy; another is to use transactions and rollback.
        # For SQLite, dropping and recreating tables per test class is often simplest.
        # Here, we'll delete all data from tables.
        session = self.TestSessionLocal()
        from june_agent.models_v2.orm_models import TaskORM, InitiativeORM # Import for delete
        session.query(TaskORM).delete()
        session.query(InitiativeORM).delete()
        session.commit()
        session.close()


    # --- Initiative Tests ---
    def test_create_and_get_initiative(self):
        init_create = InitiativeCreate(name="Test Service Init", description="Desc")
        created_schema = self.model_service.create_initiative(init_create)
        self.assertIsNotNone(created_schema)
        self.assertEqual(created_schema.name, "Test Service Init")
        self.assertIsNotNone(created_schema.id)

        retrieved_schema = self.model_service.get_initiative(created_schema.id)
        self.assertIsNotNone(retrieved_schema)
        self.assertEqual(retrieved_schema.name, "Test Service Init")

    def test_get_initiative_not_found(self):
        retrieved = self.model_service.get_initiative("non_existent_id")
        self.assertIsNone(retrieved)

    def test_get_all_initiatives(self):
        self.model_service.create_initiative(InitiativeCreate(name="Init 1"))
        self.model_service.create_initiative(InitiativeCreate(name="Init 2"))

        all_inits = self.model_service.get_all_initiatives()
        self.assertEqual(len(all_inits), 2)

    def test_update_initiative(self):
        init_create = InitiativeCreate(name="Original Name")
        created = self.model_service.create_initiative(init_create)

        update_data = InitiativeUpdate(name="Updated Name", status="active")
        updated = self.model_service.update_initiative(created.id, update_data)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "Updated Name")
        self.assertEqual(updated.status, "active")

        retrieved = self.model_service.get_initiative(created.id)
        self.assertEqual(retrieved.name, "Updated Name")

    def test_delete_initiative_and_cascade(self):
        # Create initiative
        init_create = InitiativeCreate(name="Init to Delete")
        created_init = self.model_service.create_initiative(init_create)

        # Create task for this initiative
        task_create = TaskCreate(description="Task under Init to Delete", initiative_id=created_init.id)
        # The service's create_task needs initiative_id as a separate param
        created_task = self.model_service.create_task(task_create, initiative_id=created_init.id)
        self.assertIsNotNone(self.model_service.get_task(created_task.id))

        # Delete initiative
        deleted = self.model_service.delete_initiative(created_init.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.model_service.get_initiative(created_init.id))

        # Verify task was cascade deleted
        self.assertIsNone(self.model_service.get_task(created_task.id), "Task should be cascade deleted")

    # --- Task Tests ---
    def test_create_and_get_task(self):
        init = self.model_service.create_initiative(InitiativeCreate(name="Parent Init for Task"))

        task_create_dto = TaskCreate(description="Service Test Task", initiative_id=init.id)
        created_task_schema = self.model_service.create_task(task_create_dto, initiative_id=init.id)

        self.assertIsNotNone(created_task_schema)
        self.assertEqual(created_task_schema.description, "Service Test Task")
        self.assertEqual(created_task_schema.initiative_id, init.id)
        self.assertEqual(created_task_schema.status, DomainTask.STATUS_PENDING) # Default from Pydantic/ORM

        retrieved_task_schema = self.model_service.get_task(created_task_schema.id)
        self.assertIsNotNone(retrieved_task_schema)
        self.assertEqual(retrieved_task_schema.description, "Service Test Task")

        # Test getting domain object
        retrieved_domain_task = self.model_service.get_task_domain_object(created_task_schema.id, load_subtasks=True)
        self.assertIsNotNone(retrieved_domain_task)
        self.assertIsInstance(retrieved_domain_task, DomainTask)
        self.assertEqual(retrieved_domain_task.description, "Service Test Task")


    def test_update_task(self):
        init = self.model_service.create_initiative(InitiativeCreate(name="Init for Task Update"))
        task_dto = TaskCreate(description="Original Task Desc", initiative_id=init.id)
        created_task = self.model_service.create_task(task_dto, initiative_id=init.id)

        update_dto = TaskUpdate(description="Updated Task Desc", status=DomainTask.STATUS_COMPLETED, phase=None)
        updated_task = self.model_service.update_task(created_task.id, update_dto)

        self.assertIsNotNone(updated_task)
        self.assertEqual(updated_task.description, "Updated Task Desc")
        self.assertEqual(updated_task.status, DomainTask.STATUS_COMPLETED)
        self.assertIsNone(updated_task.phase)

    def test_save_task_domain_object_new_and_update(self):
        init = self.model_service.create_initiative(InitiativeCreate(name="Init for Domain Save"))

        # New domain task
        domain_task = DomainTask(description="Domain Task New", initiative_id=init.id)
        # Manually set a specific ID if you want to predict it, or let service handle it if it can
        # domain_task.id = "domain_task_test_id_01"

        saved_schema_new = self.model_service.save_task_domain_object(domain_task)
        self.assertIsNotNone(saved_schema_new)
        self.assertEqual(saved_schema_new.description, "Domain Task New")
        self.assertEqual(saved_schema_new.id, domain_task.id) # ID should be preserved

        # Update domain task
        domain_task.status = DomainTask.STATUS_EXECUTING
        domain_task.phase = DomainTask.PHASE_EXECUTION
        # The domain object's updated_at should be set by its methods, service ensures it's persisted
        original_updated_at = saved_schema_new.updated_at

        # Simulate time passing before update
        # domain_task.updated_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=1)
        # To ensure updated_at changes, manually update the domain object's timestamp as the service will use it.
        domain_task.updated_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=1)


        saved_schema_updated = self.model_service.save_task_domain_object(domain_task)
        self.assertEqual(saved_schema_updated.status, DomainTask.STATUS_EXECUTING)
        self.assertNotEqual(saved_schema_updated.updated_at.isoformat(), original_updated_at.isoformat())


    def test_get_processable_tasks_domain_objects(self):
        init = self.model_service.create_initiative(InitiativeCreate(name="Init for Processable"))

        # Task 1: Assess
        self.model_service.create_task(TaskCreate(description="T1 Assess", status=DomainTask.STATUS_PENDING, phase=DomainTask.PHASE_ASSESSMENT), initiative_id=init.id)
        # Task 2: Executing
        self.model_service.create_task(TaskCreate(description="T2 Execute", status=DomainTask.STATUS_EXECUTING, phase=DomainTask.PHASE_EXECUTION), initiative_id=init.id)
        # Task 3: Completed (should not be fetched)
        self.model_service.create_task(TaskCreate(description="T3 Done", status=DomainTask.STATUS_COMPLETED, phase=None), initiative_id=init.id)
        # Task 4: Pending Subtasks
        self.model_service.create_task(TaskCreate(description="T4 Subtasks", status=DomainTask.STATUS_PENDING_SUBTASKS, phase=None), initiative_id=init.id)

        processable_tasks = self.model_service.get_processable_tasks_domain_objects()
        self.assertEqual(len(processable_tasks), 3) # T1, T2, T4
        for task_domain in processable_tasks:
            self.assertIsInstance(task_domain, DomainTask)
            self.assertIn(task_domain.status, [DomainTask.STATUS_PENDING, DomainTask.STATUS_EXECUTING, DomainTask.STATUS_PENDING_SUBTASKS])


    def test_task_subtask_relationship_and_cascade_delete(self):
        init = self.model_service.create_initiative(InitiativeCreate(name="Init for Subtasks"))

        parent_task_dto = TaskCreate(description="Parent Task")
        parent_schema = self.model_service.create_task(parent_task_dto, initiative_id=init.id)

        sub_task_dto = TaskCreate(description="Subtask", parent_task_id=parent_schema.id)
        sub_schema = self.model_service.create_task(sub_task_dto, initiative_id=init.id) # Subtask also needs init_id

        # Verify parent_task_id on subtask
        retrieved_sub_schema = self.model_service.get_task(sub_schema.id)
        self.assertEqual(retrieved_sub_schema.parent_task_id, parent_schema.id)

        # Verify subtask is listed in parent's details (if get_task or get_task_domain_object populates it)
        parent_domain_obj = self.model_service.get_task_domain_object(parent_schema.id, load_subtasks=True)
        self.assertIsNotNone(parent_domain_obj)
        self.assertEqual(len(parent_domain_obj.subtasks), 1)
        self.assertEqual(parent_domain_obj.subtasks[0].id, sub_schema.id)

        # Test cascade delete of subtask when parent is deleted
        self.model_service.delete_task(parent_schema.id)
        self.assertIsNone(self.model_service.get_task(parent_schema.id))
        self.assertIsNone(self.model_service.get_task(sub_schema.id), "Subtask should be cascade deleted")

    def test_ensure_initial_data(self):
        init_id = "default_init_svc_test"
        task_id = "default_task_svc_test"
        self.model_service.ensure_initial_data(init_id, task_id)

        self.assertIsNotNone(self.model_service.get_initiative(init_id))
        self.assertIsNotNone(self.model_service.get_task(task_id))
        # Call again to ensure idempotency
        self.model_service.ensure_initial_data(init_id, task_id)


if __name__ == '__main__':
    # Need to ensure create_engine and sessionmaker are properly imported for test setup
    # from sqlalchemy import create_engine # Already imported at top level of module
    # from sqlalchemy.orm import sessionmaker # Already imported at top level of module
    unittest.main()
