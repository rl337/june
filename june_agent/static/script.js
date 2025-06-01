// June Agent UI client-side logic

function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, function (match) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[match];
    });
}

// Fetch and Display Agent Logs (implementation from previous version, assumed correct)
function fetchAndDisplayLogsImplementation() {
    const agentLogDiv = document.getElementById('agent-log');
    if (!agentLogDiv) {
        console.error("Agent log container 'agent-log' not found.");
        return;
    }
    fetch('/logs')
        .then(response => response.ok ? response.json() : Promise.reject(response.status))
        .then(logs => {
            agentLogDiv.innerHTML = '';
            if (!Array.isArray(logs) || logs.length === 0) {
                agentLogDiv.innerHTML = '<p>No agent logs available.</p>'; return;
            }
            const ul = document.createElement('ul');
            ul.className = 'logs';
            logs.slice().reverse().forEach(logEntry => {
                const li = document.createElement('li');
                li.className = 'log-item';
                li.textContent = escapeHTML(String(logEntry));
                ul.appendChild(li);
            });
            agentLogDiv.appendChild(ul);
        })
        .catch(error => {
            console.error('Error fetching agent logs:', error);
            if (agentLogDiv) agentLogDiv.innerHTML = '<p>Error loading agent logs.</p>';
        });
}


document.addEventListener('DOMContentLoaded', () => {
    const agentStatusElement = document.getElementById('agent-status');
    const detailedStatusCountsElement = document.getElementById('detailed-status-counts');
    const createTaskForm = document.getElementById('create-task-form');
    const initiativeSelectElement = document.getElementById('initiative-select');
    const taskDescriptionInput = document.getElementById('task-description');
    const initiativesListDiv = document.getElementById('initiatives-list');
    const tasksListDiv = document.getElementById('tasks-list');
    const formMessageDiv = document.getElementById('form-message');

    window.fetchAndDisplayLogs = fetchAndDisplayLogsImplementation;

    async function fetchAgentStatus() {
        if (!agentStatusElement || !detailedStatusCountsElement) return;
        try {
            const response = await fetch('/status');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            agentStatusElement.textContent = `${escapeHTML(data.agent_overall_status)} (Initiatives: ${data.total_initiatives}, Tasks: ${data.total_tasks})`;

            detailedStatusCountsElement.innerHTML = '<strong>Task Statuses:</strong><ul>';
            for (const status in data.status_counts) {
                detailedStatusCountsElement.innerHTML += `<li>${escapeHTML(status)}: ${data.status_counts[status]}</li>`;
            }
            detailedStatusCountsElement.innerHTML += '</ul>';

        } catch (error) {
            console.error('Failed to fetch agent status:', error);
            agentStatusElement.textContent = 'Error loading status';
            detailedStatusCountsElement.innerHTML = '';
        }
    }

    async function fetchAndDisplayInitiatives() {
        if (!initiativesListDiv || !initiativeSelectElement) return;
        try {
            const response = await fetch('/initiatives');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const initiatives = await response.json();

            initiativesListDiv.innerHTML = '';
            initiativeSelectElement.innerHTML = '<option value="">-- Select an Initiative --</option>';

            if (initiatives.length === 0) {
                initiativesListDiv.innerHTML = '<p>No initiatives found.</p>';
                return;
            }

            const ul = document.createElement('ul');
            ul.className = 'initiatives';
            initiatives.forEach(init => {
                const li = document.createElement('li');
                li.className = `initiative-item status-${escapeHTML(init.status ? init.status.toLowerCase() : 'unknown')}`;
                li.innerHTML = `
                    <div class="initiative-id"><strong>ID:</strong> ${escapeHTML(init.id)}</div>
                    <div class="initiative-name"><strong>Name:</strong> ${escapeHTML(init.name)}</div>
                    <div class="initiative-description"><strong>Description:</strong> ${escapeHTML(init.description)}</div>
                    <div class="initiative-status"><strong>Status:</strong> ${escapeHTML(init.status)}</div>
                    <div class="initiative-tasks"><strong>Tasks (${init.task_ids.length}):</strong> ${escapeHTML(init.task_ids.join(', '))}</div>
                    <div class="initiative-created"><strong>Created:</strong> ${escapeHTML(new Date(init.created_at).toLocaleString())}</div>
                `;
                ul.appendChild(li);

                // Populate select dropdown
                const option = document.createElement('option');
                option.value = escapeHTML(init.id);
                option.textContent = escapeHTML(init.name) + ` (ID: ${escapeHTML(init.id.substring(0,8))}...)`;
                initiativeSelectElement.appendChild(option);
            });
            initiativesListDiv.appendChild(ul);
            if (initiatives.length > 0 && initiativeSelectElement.options.length > 1) {
                 // Pre-select the first initiative if available and not the placeholder
                // initiativeSelectElement.value = initiatives[0].id;
            }


        } catch (error) {
            console.error('Error fetching initiatives:', error);
            if (initiativesListDiv) initiativesListDiv.innerHTML = '<p>Error loading initiatives.</p>';
            initiativeSelectElement.innerHTML = '<option value="">Error loading</option>';
        }
    }

    async function fetchAndDisplayTasks() {
        if (!tasksListDiv) return;
        // Optional: Add filter by selected initiative later
        // const selectedInitiativeId = initiativeSelectElement.value;
        // const fetchUrl = selectedInitiativeId ? `/tasks?initiative_id=${selectedInitiativeId}` : '/tasks';
        const fetchUrl = '/tasks';

        try {
            const response = await fetch(fetchUrl);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const tasks = await response.json();

            tasksListDiv.innerHTML = '';
            if (tasks.length === 0) {
                tasksListDiv.innerHTML = '<p>No tasks found.</p>'; return;
            }

            const ul = document.createElement('ul');
            ul.className = 'tasks';
            tasks.forEach(task => {
                const li = document.createElement('li');
                li.className = `task-item status-${escapeHTML(task.status ? task.status.toLowerCase() : 'unknown')}`;
                let subtaskInfo = task.subtask_ids && task.subtask_ids.length > 0 ? `(${task.subtask_ids.join(', ')})` : '(none)';
                li.innerHTML = `
                    <div class="task-id"><strong>ID:</strong> ${escapeHTML(task.id)}</div>
                    <div class="task-description"><strong>Description:</strong> ${escapeHTML(task.description)}</div>
                    <div class="task-status"><strong>Status:</strong> ${escapeHTML(task.status)}</div>
                    <div class="task-phase"><strong>Phase:</strong> ${escapeHTML(task.phase || 'N/A')}</div>
                    <div class="task-initiative"><strong>Initiative ID:</strong> ${escapeHTML(task.initiative_id || 'N/A')}</div>
                    <div class="task-parent"><strong>Parent Task ID:</strong> ${escapeHTML(task.parent_task_id || 'N/A')}</div>
                    <div class="task-subtasks"><strong>Subtasks ${task.num_subtasks || 0}:</strong> ${escapeHTML(subtaskInfo)}</div>
                    ${task.result ? `<div class="task-result"><strong>Result:</strong> <pre>${escapeHTML(task.result)}</pre></div>` : ''}
                    ${task.error_message ? `<div class="task-error"><strong>Error:</strong> <pre>${escapeHTML(task.error_message)}</pre></div>` : ''}
                    <div class="task-created"><strong>Created:</strong> ${escapeHTML(new Date(task.created_at).toLocaleString())}</div>
                `;
                ul.appendChild(li);
            });
            tasksListDiv.appendChild(ul);
        } catch (error) {
            console.error('Error fetching tasks:', error);
            if (tasksListDiv) tasksListDiv.innerHTML = '<p>Error loading tasks.</p>';
        }
    }

    if (createTaskForm) {
        createTaskForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const description = taskDescriptionInput.value.trim();
            const initiativeId = initiativeSelectElement.value;

            if (!description) {
                formMessageDiv.textContent = 'Task description cannot be empty.';
                formMessageDiv.className = 'message error'; return;
            }
            if (!initiativeId) {
                formMessageDiv.textContent = 'Please select an initiative.';
                formMessageDiv.className = 'message error'; return;
            }
            formMessageDiv.textContent = ''; formMessageDiv.className = 'message';

            try {
                const response = await fetch('/tasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description: description, initiative_id: initiativeId }),
                });
                if (!response.ok) {
                    const errData = await response.json().catch(() => ({error: `Server error: ${response.status}`}));
                    throw new Error(errData.error || `Server error: ${response.status}`);
                }
                const data = await response.json();
                formMessageDiv.textContent = 'Task created successfully! (ID: ' + data.id + ')';
                formMessageDiv.className = 'message success';
                taskDescriptionInput.value = '';
                // initiativeSelectElement.value = ''; // Optionally reset initiative selection

                fetchAndDisplayTasks(); // Refresh tasks list
                fetchAgentStatus();     // Refresh status
                window.fetchAndDisplayLogs(); // Refresh logs
            } catch (error) {
                console.error('Error creating task:', error);
                formMessageDiv.textContent = 'Error creating task: ' + error.message;
                formMessageDiv.className = 'message error';
            }
        });
    }

    // Initial data fetch
    fetchAgentStatus();
    fetchAndDisplayInitiatives(); // Fetch initiatives first to populate dropdown
    fetchAndDisplayTasks();
    window.fetchAndDisplayLogs();

    // Polling
    const POLLING_INTERVAL = 7500;
    setInterval(() => {
        fetchAgentStatus();
        fetchAndDisplayInitiatives(); // Keep initiative list (and dropdown) updated
        fetchAndDisplayTasks();
        window.fetchAndDisplayLogs();
    }, POLLING_INTERVAL);
});
