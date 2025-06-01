import unittest
import os
import json
from june_agent.web_service import create_app
from june_agent.db import DatabaseManager
from june_agent.initiative import Initiative
from june_agent.task import Task

TEST_DB_PATH_WS = 'test_june_agent_webservice.db'

class TestWebService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure no old test DB is lying around
        if os.path.exists(TEST_DB_PATH_WS):
            os.remove(TEST_DB_PATH_WS)

    def setUp(self):
        self.db_manager = DatabaseManager(db_path=TEST_DB_PATH_WS)
        self.db_manager.connect()
        self.db_manager.create_tables()

        # Create a list for agent_logs_ref as the app expects it
        self.agent_logs = []

        self.app = create_app(db_manager_ref=self.db_manager, agent_logs_ref=self.agent_logs)
        self.app.config.update({"TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.db_manager.close()
        if os.path.exists(TEST_DB_PATH_WS):
            os.remove(TEST_DB_PATH_WS)

    # Helper to add an initiative
    def _add_initiative(self, name="Test Initiative", description="Test Desc", init_id=None):
        initiative = Initiative(name=name, description=description, db_manager=self.db_manager, initiative_id=init_id)
        initiative.save()
        return initiative

    # Helper to add a task
    def _add_task(self, description="Test Task", initiative_id=None, task_id=None, status=Task.STATUS_PENDING, phase=Task.PHASE_ASSESSMENT):
        task = Task(description=description, db_manager=self.db_manager, initiative_id=initiative_id, task_id=task_id, status=status, phase=phase)
        task.save()
        return task

    # --- Test /status ---
    def test_get_status_empty_db(self):
        response = self.client.get('/status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['agent_overall_status'], 'idle')
        self.assertEqual(data['total_initiatives'], 0)
        self.assertEqual(data['total_tasks'], 0)
        for status_key in data['status_counts']:
            self.assertEqual(data['status_counts'][status_key], 0)

    def test_get_status_with_data(self):
        init1 = self._add_initiative(name="Main Init", init_id="init_status_1")
        self._add_task(description="Pending Task", initiative_id=init1.id, status=Task.STATUS_PENDING)
        self._add_task(description="Executing Task", initiative_id=init1.id, status=Task.STATUS_EXECUTING)
        self._add_task(description="Completed Task", initiative_id=init1.id, status=Task.STATUS_COMPLETED)

        response = self.client.get('/status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['agent_overall_status'], 'processing') # Due to executing task
        self.assertEqual(data['total_initiatives'], 1)
        self.assertEqual(data['total_tasks'], 3)
        self.assertEqual(data['status_counts'][Task.STATUS_PENDING], 1)
        self.assertEqual(data['status_counts'][Task.STATUS_EXECUTING], 1)
        self.assertEqual(data['status_counts'][Task.STATUS_COMPLETED], 1)
        self.assertEqual(data['status_counts'][Task.STATUS_FAILED], 0)

    # --- Test /initiatives ---
    def test_get_initiatives_empty(self):
        response = self.client.get('/initiatives')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), [])

    def test_get_initiatives_with_data(self):
        init1 = self._add_initiative(name="Alpha Initiative", init_id="init_alpha")
        init2 = self._add_initiative(name="Beta Initiative", init_id="init_beta")
        # Add a task to init1 to test task_ids in response
        task1 = self._add_task(description="Task for Alpha", initiative_id=init1.id)

        response = self.client.get('/initiatives')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        # Order might vary, so check for presence
        returned_init_names = sorted([i['name'] for i in data])
        self.assertListEqual(returned_init_names, ["Alpha Initiative", "Beta Initiative"])

        # Check task_ids for Alpha Initiative
        alpha_data = next(i for i in data if i['id'] == init1.id)
        self.assertIn(task1.id, alpha_data['task_ids'])


    def test_get_single_initiative(self):
        init1 = self._add_initiative(name="Detail Initiative", init_id="init_detail_1")
        task1 = self._add_task(description="Task for Detail", initiative_id=init1.id)

        response = self.client.get(f'/initiatives/{init1.id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['id'], init1.id)
        self.assertEqual(data['name'], "Detail Initiative")
        self.assertIn(task1.id, data['task_ids'])

    def test_get_single_initiative_not_found(self):
        response = self.client.get('/initiatives/non_existent_init_id')
        self.assertEqual(response.status_code, 404)

    # --- Test /tasks ---
    def test_get_tasks_empty(self):
        response = self.client.get('/tasks')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), [])

    def test_post_task_valid(self):
        init1 = self._add_initiative(name="Task Holder Init", init_id="init_task_holder")

        task_data = {'description': 'New Task via POST', 'initiative_id': init1.id}
        response = self.client.post('/tasks', json=task_data)
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['description'], 'New Task via POST')
        self.assertEqual(data['initiative_id'], init1.id)
        self.assertEqual(data['status'], Task.STATUS_PENDING)
        self.assertEqual(data['phase'], Task.PHASE_ASSESSMENT)

        # Verify in DB
        loaded_task = Task.load(data['id'], self.db_manager)
        self.assertIsNotNone(loaded_task)
        self.assertEqual(loaded_task.description, 'New Task via POST')

    def test_post_task_missing_fields(self):
        response = self.client.post('/tasks', json={'description': 'Incomplete'})
        self.assertEqual(response.status_code, 400) # Missing initiative_id

        response = self.client.post('/tasks', json={'initiative_id': 'some_init'})
        self.assertEqual(response.status_code, 400) # Missing description

    def test_post_task_initiative_not_found(self):
        task_data = {'description': 'Task for ghost init', 'initiative_id': 'ghost_init_id'}
        response = self.client.post('/tasks', json=task_data)
        self.assertEqual(response.status_code, 404) # Initiative not found

    def test_get_tasks_with_data_and_filter(self):
        init1 = self._add_initiative(init_id="filter_init_1")
        init2 = self._add_initiative(init_id="filter_init_2")
        task1_init1 = self._add_task(description="T1 I1", initiative_id=init1.id)
        task2_init1 = self._add_task(description="T2 I1", initiative_id=init1.id)
        task1_init2 = self._add_task(description="T1 I2", initiative_id=init2.id)

        # Get all tasks
        response_all = self.client.get('/tasks')
        self.assertEqual(response_all.status_code, 200)
        data_all = json.loads(response_all.data)
        self.assertEqual(len(data_all), 3)

        # Get tasks for init1
        response_init1 = self.client.get(f'/tasks?initiative_id={init1.id}')
        self.assertEqual(response_init1.status_code, 200)
        data_init1 = json.loads(response_init1.data)
        self.assertEqual(len(data_init1), 2)
        for task_dict in data_init1:
            self.assertEqual(task_dict['initiative_id'], init1.id)

    def test_get_single_task(self):
        init1 = self._add_initiative(init_id="single_task_init")
        task1 = self._add_task(description="My Test Task Detail", initiative_id=init1.id, task_id="task_detail_001")

        # Add a subtask to task1 to test subtask_ids in response
        subtask = self._add_task(description="Subtask for Detail", initiative_id=init1.id)
        task1.add_subtask(subtask) # This saves subtask and updates parent (parent needs re-saving for status)
        task1.save() # Re-save parent task if add_subtask modified it

        response = self.client.get(f'/tasks/{task1.id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['id'], task1.id)
        self.assertEqual(data['description'], "My Test Task Detail")
        self.assertIn(subtask.id, data['subtask_ids'])

    def test_get_single_task_not_found(self):
        response = self.client.get('/tasks/non_existent_task_id')
        self.assertEqual(response.status_code, 404)

    # --- Test /logs ---
    def test_get_agent_logs_empty(self):
        response = self.client.get('/logs')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), [])

    def test_get_agent_logs_with_data(self):
        self.agent_logs.append("Log entry 1")
        self.agent_logs.append("Log entry 2")

        response = self.client.get('/logs')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertListEqual(data, ["Log entry 1", "Log entry 2"])


if __name__ == '__main__':
    unittest.main()
