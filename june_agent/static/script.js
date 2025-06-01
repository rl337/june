// June Agent UI client-side logic

// Helper function to prevent XSS
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, function (match) {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[match];
    });
}

// This will be assigned to window.fetchAndDisplayLogs within DOMContentLoaded
function fetchAndDisplayLogsImplementation() {
    const agentLogDiv = document.getElementById('agent-log');
    if (!agentLogDiv) {
        console.error("Agent log container 'agent-log' not found.");
        return;
    }

    fetch('/logs')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(logs => {
            agentLogDiv.innerHTML = ''; // Clear previous logs

            if (!Array.isArray(logs) || logs.length === 0) {
                agentLogDiv.innerHTML = '<p>No agent logs available.</p>';
                return;
            }

            const ul = document.createElement('ul');
            ul.className = 'logs'; // For styling
            // Display logs, newest first by reversing the client-side array.
            logs.slice().reverse().forEach(logEntry => {
                const li = document.createElement('li');
                li.className = 'log-item';
                // Assuming logEntry is a string, escape it
                li.textContent = escapeHTML(String(logEntry));
                ul.appendChild(li);
            });
            agentLogDiv.appendChild(ul);
        })
        .catch(error => {
            console.error('Error fetching agent logs:', error);
            if (agentLogDiv) {
                agentLogDiv.innerHTML = '<p>Error loading agent logs.</p>';
            }
        });
}


document.addEventListener('DOMContentLoaded', () => {
    // Element references
    const agentStatusElement = document.getElementById('agent-status');
    const createTaskForm = document.getElementById('create-task-form');
    const taskDescriptionInput = document.getElementById('task-description');
    const tasksListDiv = document.getElementById('tasks-list');
    const formMessageDiv = document.getElementById('form-message');
    const agentLogElement = document.getElementById('agent-log'); // Used by fetchAndDisplayLogsImplementation

    // Assign the log fetching function to the window object or ensure it's callable
    window.fetchAndDisplayLogs = fetchAndDisplayLogsImplementation;


    // Function to fetch agent status (using async/await for consistency)
    async function fetchAgentStatus() {
        if (!agentStatusElement) return;
        try {
            const response = await fetch('/status');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            agentStatusElement.textContent =
                `${data.agent_overall_status} (Total: ${data.total_tasks}, ` +
                `Pending: ${data.pending_tasks}, Processing: ${data.processing_tasks}, ` +
                `Completed: ${data.completed_tasks}, Failed: ${data.failed_tasks})`;
        } catch (error) {
            console.error('Failed to fetch agent status:', error);
            agentStatusElement.textContent = 'Error loading status';
        }
    }

    // Function to fetch and display tasks (refined version)
    function fetchAndDisplayTasks() {
        if (!tasksListDiv) {
            console.error("Task list container 'tasks-list' not found.");
            return;
        }

        fetch('/tasks')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(tasks => {
                tasksListDiv.innerHTML = ''; // Clear previous tasks

                if (tasks.length === 0) {
                    tasksListDiv.innerHTML = '<p>No tasks found.</p>';
                    return;
                }

                const ul = document.createElement('ul');
                ul.className = 'tasks';
                tasks.forEach(task => {
                    const li = document.createElement('li');
                    li.className = `task-item status-${escapeHTML(task.status ? task.status.toLowerCase() : 'unknown')}`;

                    let taskHTML = `
                        <div class="task-id"><strong>ID:</strong> ${escapeHTML(task.id)}</div>
                        <div class="task-description"><strong>Description:</strong> ${escapeHTML(task.description)}</div>
                        <div class="task-status"><strong>Status:</strong> ${escapeHTML(task.status)}</div>
                    `;

                    if (task.result) {
                        taskHTML += `<div class="task-result"><strong>Result:</strong> <pre>${escapeHTML(task.result)}</pre></div>`;
                    }
                    if (task.error_message) {
                        taskHTML += `<div class="task-error"><strong>Error:</strong> <pre>${escapeHTML(task.error_message)}</pre></div>`;
                    }
                    if (task.num_requests !== undefined) {
                         taskHTML += `<div class="task-requests"><strong>Requests:</strong> ${task.num_requests}</div>`;
                    }

                    li.innerHTML = taskHTML;
                    ul.appendChild(li);
                });
                tasksListDiv.appendChild(ul);
            })
            .catch(error => {
                console.error('Error fetching tasks:', error);
                if (tasksListDiv) {
                    tasksListDiv.innerHTML = '<p>Error loading tasks. Please try again later.</p>';
                }
            });
    }

    // Handle task creation form submission
    if (createTaskForm) {
        createTaskForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            const description = taskDescriptionInput.value.trim();

            if (!description) {
                if(formMessageDiv) {
                    formMessageDiv.textContent = 'Task description cannot be empty.';
                    formMessageDiv.className = 'message error';
                } else {
                    alert('Task description cannot be empty.');
                }
                return;
            }

            if(formMessageDiv) {
                formMessageDiv.textContent = '';
                formMessageDiv.className = 'message';
            }

            try {
                const response = await fetch('/tasks', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ description: description }),
                });

                if (!response.ok) {
                    let errorMsg = `Server error: ${response.status}`;
                    try {
                        const errData = await response.json();
                        errorMsg = errData.error || errorMsg;
                    } catch (e) {
                        console.warn("Could not parse error response as JSON", e);
                    }
                    throw new Error(errorMsg);
                }

                const data = await response.json();

                if(formMessageDiv) {
                    formMessageDiv.textContent = 'Task created successfully! (ID: ' + data.id + ')';
                    formMessageDiv.className = 'message success';
                }
                taskDescriptionInput.value = '';

                fetchAndDisplayTasks();
                fetchAgentStatus();
                window.fetchAndDisplayLogs(); // Refresh logs after task creation as well
            } catch (error) {
                console.error('Error creating task:', error);
                if(formMessageDiv) {
                    formMessageDiv.textContent = 'Error creating task: ' + error.message;
                    formMessageDiv.className = 'message error';
                } else {
                    alert('Error creating task: ' + error.message);
                }
            }
        });
    }

    // Initial data fetch
    fetchAgentStatus();
    fetchAndDisplayTasks();
    window.fetchAndDisplayLogs(); // Call the implemented function

    // Set up polling to refresh data periodically
    const POLLING_INTERVAL = 7500; // milliseconds (e.g., 7.5 seconds)

    setInterval(function() {
        console.log("Polling for updates..."); // Optional: for debugging polling
        if (typeof fetchAgentStatus === 'function') {
            fetchAgentStatus();
        }
        if (typeof fetchAndDisplayTasks === 'function') {
            fetchAndDisplayTasks();
        }
        if (typeof window.fetchAndDisplayLogs === 'function') {
            window.fetchAndDisplayLogs();
        }
    }, POLLING_INTERVAL);
});
