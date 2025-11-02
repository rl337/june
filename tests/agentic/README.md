# Agentic Capabilities Testing Framework

Comprehensive testing framework for June's agentic capabilities system, ensuring reliability, safety, and performance.

## Overview

This framework provides testing for all aspects of agentic capabilities:

1. **Agent Unit Tests** - Test individual agent components (planning, execution, verification)
2. **Integration Tests** - Test agent interactions with external services
3. **Simulation Environment** - Safe testing environment with mocked operations
4. **Performance Tests** - Benchmarks and performance validation
5. **Safety Tests** - Security and safety validation
6. **Regression Tests** - Ensure existing capabilities still work

## Structure

```
tests/agentic/
??? unit/                    # Agent unit tests
?   ??? test_agent_planning.py
?   ??? test_execution_strategies.py
?   ??? test_verification_logic.py
??? integration/             # Integration tests
?   ??? test_todo_service_integration.py
?   ??? test_code_execution_integration.py
??? simulation/               # Simulation environment
?   ??? mock_git.py
?   ??? mock_task_service.py
?   ??? mock_execution.py
??? performance/             # Performance tests
?   ??? test_agent_performance.py
??? safety/                   # Safety tests
?   ??? test_security_boundaries.py
??? regression/               # Regression tests
    ??? test_common_workflows.py
```

## Running Tests

### Run All Agentic Tests

```bash
# Run all agentic tests
pytest tests/agentic/ -v

# Run with coverage
pytest tests/agentic/ --cov=tests/agentic --cov-report=html

# Run specific test category
pytest tests/agentic/unit/ -v
pytest tests/agentic/integration/ -v
pytest tests/agentic/performance/ -v
pytest tests/agentic/safety/ -v
pytest tests/agentic/regression/ -v
```

### Run Specific Test Files

```bash
pytest tests/agentic/unit/test_agent_planning.py -v
pytest tests/agentic/integration/test_todo_service_integration.py -v
```

### Run with Markers

```bash
# Run only unit tests
pytest tests/agentic/ -m unit -v

# Run only integration tests
pytest tests/agentic/ -m integration -v

# Skip slow tests
pytest tests/agentic/ -m "not slow" -v
```

## Simulation Environment

The simulation environment provides safe testing without affecting real systems:

### Mock Task Service

```python
from tests.agentic.simulation.mock_task_service import MockTaskService, TaskType

service = MockTaskService()
project = service.create_project(
    name="Test Project",
    description="Test",
    origin_url="https://test.com",
    local_path="/tmp/test"
)

task = service.create_task(
    project_id=project.id,
    title="Test Task",
    task_type=TaskType.CONCRETE,
    task_instruction="Do something",
    verification_instruction="Verify it",
    agent_id="test-agent"
)
```

### Mock Git Operations

```python
from tests.agentic.simulation.mock_git import GitSimulator

git = GitSimulator.create_mock_repo()
git.commit("Add feature")
git.push("origin", "main")
```

### Mock Execution Environment

```python
from tests.agentic.simulation.mock_execution import ExecutionSimulator

env = ExecutionSimulator.create_mock_env()
env.write_file("test.py", "print('hello')")
result = env.execute_command("python test.py")
```

## Test Coverage

### Unit Tests

- **Planning Logic**: Task analysis, decomposition, dependency identification
- **Execution Strategies**: Strategy selection, code generation
- **Verification Logic**: Test execution, quality checks, coverage

### Integration Tests

- **TODO Service**: Task discovery, reservation, updates, completion
- **Code Execution**: File operations, test execution, git operations
- **End-to-End**: Complete workflows from task creation to completion

### Performance Tests

- Task reservation performance (< 100ms)
- Concurrent task processing
- Resource usage profiling
- Scalability (handles 1000+ tasks)

### Safety Tests

- Blocks dangerous operations (rm -rf /)
- Prevents directory traversal
- Validates commit messages
- Enforces resource limits
- Error recovery mechanisms

### Regression Tests

- Basic task workflow
- Task with git operations
- Task with test execution
- Task unlock on error
- Multiple agents coordination

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:

```yaml
# Example CI configuration
test_agentic:
  script:
    - pytest tests/agentic/ -v --cov=tests/agentic --cov-report=xml
  coverage: '/TOTAL.*\s+(\d+%)$/'
```

## Best Practices

1. **Use Simulation Environment**: Always use mock services for testing
2. **Test Isolation**: Each test should be independent and not rely on shared state
3. **Performance Baselines**: Update performance baselines when optimizing
4. **Safety First**: All dangerous operations must be blocked in tests
5. **Coverage**: Maintain high test coverage (target: 80%+)

## Contributing

When adding new agent capabilities:

1. Add unit tests for new components
2. Add integration tests for new service interactions
3. Add regression tests for common workflows
4. Update performance baselines if needed
5. Add safety tests for any new operations

## Troubleshooting

### Tests Failing

- Check that simulation environment is properly cleaned up
- Verify mock services are initialized correctly
- Check test isolation (tests shouldn't share state)

### Performance Issues

- Review performance test baselines
- Check for memory leaks in long-running tests
- Verify resource cleanup

### Safety Test Failures

- Critical: These tests must pass before merging
- Review security boundaries
- Verify dangerous operations are blocked
