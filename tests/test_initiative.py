import unittest
import os
from june_agent.db import DatabaseManager
from june_agent.initiative import Initiative
from june_agent.task import Task # Needed for adding task objects

TEST_DB_PATH = 'test_june_agent_initiative_unittest.db'

class TestInitiative(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def setUp(self):
        self.db_manager = DatabaseManager(db_path=TEST_DB_PATH)
        self.db_manager.connect()
        self.db_manager.create_tables()

    def tearDown(self):
        self.db_manager.close()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_create_initiative_and_save(self):
        name = "Test Initiative Alpha"
        description = "Description for test initiative Alpha."
        initiative = Initiative(name=name, description=description, db_manager=self.db_manager)

        # Check properties before save
        self.assertIsNotNone(initiative.id)
        self.assertEqual(initiative.name, name)
        self.assertEqual(initiative.description, description)
        self.assertEqual(initiative.status, 'pending') # Default status
        self.assertIsNotNone(initiative.created_at)
        self.assertIsNotNone(initiative.updated_at)
        self.assertEqual(initiative.created_at, initiative.updated_at)

        initiative.save()

        # Load from DB to verify
        loaded_initiative = Initiative.load(initiative.id, self.db_manager)
        self.assertIsNotNone(loaded_initiative)
        self.assertEqual(loaded_initiative.name, name)
        self.assertEqual(loaded_initiative.description, description)
        self.assertEqual(loaded_initiative.status, 'pending')
        self.assertEqual(loaded_initiative.id, initiative.id)

    def test_load_initiative_not_found(self):
        loaded_initiative = Initiative.load("non_existent_id", self.db_manager)
        self.assertIsNone(loaded_initiative)

    def test_update_status_and_save(self):
        initiative = Initiative(name="Status Update Test", description="Desc", db_manager=self.db_manager)
        initiative.save()
        original_updated_at = initiative.updated_at

        # Wait a tiny moment to ensure timestamp can change
        import time
        time.sleep(0.01)

        initiative.update_status("active")
        self.assertEqual(initiative.status, "active")
        # update_status calls save, so it should be persisted

        loaded_initiative = Initiative.load(initiative.id, self.db_manager)
        self.assertIsNotNone(loaded_initiative)
        self.assertEqual(loaded_initiative.status, "active")
        self.assertNotEqual(loaded_initiative.updated_at, original_updated_at)

    def test_add_task_object(self):
        initiative = Initiative(name="Task Container Initiative", description="Desc", db_manager=self.db_manager)
        # Task needs db_manager too, and potentially initiative_id upon creation
        # For this test, we are testing add_task_object which primarily updates in-memory list
        # and sets task.initiative_id
        task1_desc = "Sub-task 1 for initiative"
        task1 = Task(description=task1_desc, db_manager=self.db_manager, initiative_id=initiative.id)
        # task1.save() # Task save is not strictly part of initiative.add_task_object's responsibility

        initiative.add_task_object(task1)
        self.assertIn(task1, initiative.tasks)
        self.assertEqual(len(initiative.tasks), 1)
        self.assertEqual(task1.initiative_id, initiative.id)

        # Add the same task again (should not duplicate)
        initiative.add_task_object(task1)
        self.assertEqual(len(initiative.tasks), 1)

    def test_to_dict_representation(self):
        name = "Dict Test Initiative"
        initiative = Initiative(name=name, description="Dict Desc", db_manager=self.db_manager)
        initiative.save() # Save to ensure all fields are set as they would be when loaded

        # Add a task to test 'task_ids' in dict
        task_for_dict = Task(description="Task for dict", db_manager=self.db_manager, initiative_id=initiative.id)
        # task_for_dict.save() # Not strictly needed for this test of to_dict's list comprehension
        initiative.add_task_object(task_for_dict)


        initiative_dict = initiative.to_dict()

        self.assertEqual(initiative_dict['id'], initiative.id)
        self.assertEqual(initiative_dict['name'], name)
        self.assertEqual(initiative_dict['status'], 'pending')
        self.assertIsNotNone(initiative_dict['created_at'])
        self.assertIsNotNone(initiative_dict['updated_at'])
        self.assertEqual(initiative_dict['num_tasks'], 1)
        self.assertListEqual(initiative_dict['task_ids'], [task_for_dict.id])

    def test_load_all_initiatives(self):
        initiatives_data = [
            {"name": "Initiative Load All 1", "description": "Desc 1"},
            {"name": "Initiative Load All 2", "description": "Desc 2"},
        ]
        created_ids = []
        for data in initiatives_data:
            init = Initiative(name=data["name"], description=data["description"], db_manager=self.db_manager)
            init.save()
            created_ids.append(init.id)

        loaded_initiatives = Initiative.load_all(self.db_manager)
        self.assertEqual(len(loaded_initiatives), 2)

        loaded_ids = sorted([init.id for init in loaded_initiatives])
        self.assertListEqual(sorted(created_ids), loaded_ids)

    def test_initiative_save_idempotency(self):
        # Test that saving an existing initiative updates it rather than creating a new one or failing.
        name = "Idempotent Save Test"
        initiative = Initiative(name=name, description="Initial Description", db_manager=self.db_manager)
        initiative.save()
        original_id = initiative.id
        original_created_at = initiative.created_at

        # Modify and save again
        initiative.description = "Updated Description"
        initiative.status = "active"

        import time # ensure updated_at changes
        time.sleep(0.01)
        initiative.save() # This should be an UPDATE

        # Verify no new record was created and existing one is updated
        count_query = "SELECT COUNT(*) FROM initiatives WHERE id = ?"
        count_result = self.db_manager.fetch_one(count_query, (original_id,))
        self.assertEqual(count_result[0], 1, "Should only be one record with this ID.")

        loaded_initiative = Initiative.load(original_id, self.db_manager)
        self.assertIsNotNone(loaded_initiative)
        self.assertEqual(loaded_initiative.id, original_id)
        self.assertEqual(loaded_initiative.name, name) # Name was not changed
        self.assertEqual(loaded_initiative.description, "Updated Description")
        self.assertEqual(loaded_initiative.status, "active")
        self.assertEqual(loaded_initiative.created_at, original_created_at, "created_at should not change on update.")
        self.assertNotEqual(loaded_initiative.updated_at, original_created_at, "updated_at should change.")

if __name__ == '__main__':
    unittest.main()
