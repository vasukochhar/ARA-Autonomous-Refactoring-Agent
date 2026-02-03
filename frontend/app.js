/**
 * ARA Dashboard - Frontend JavaScript
 * Handles workflow management and API communication
 */

// Configuration
const API_BASE_URL = 'http://localhost:8000';

// State
let currentWorkflowId = null;
let workflows = [];
let pollInterval = null;

// ============================================================================
// API Functions
// ============================================================================

async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };

    const response = await fetch(url, { ...defaultOptions, ...options });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

async function loadWorkflows() {
    try {
        workflows = await fetchAPI('/workflows');
        renderWorkflowList();
        updateStats();
    } catch (error) {
        console.error('Failed to load workflows:', error);
        showToast('Failed to load workflows', 'error');
    }
}

async function startWorkflowAPI(goal, files, maxIterations) {
    return fetchAPI('/start_refactor', {
        method: 'POST',
        body: JSON.stringify({
            refactoring_goal: goal,
            files: files,
            max_iterations: maxIterations,
        }),
    });
}

async function getWorkflowStatus(workflowId) {
    return fetchAPI(`/get_status/${workflowId}`);
}

async function resumeWorkflowAPI(workflowId, action, feedback = null) {
    return fetchAPI(`/resume_workflow/${workflowId}`, {
        method: 'POST',
        body: JSON.stringify({ action, feedback }),
    });
}

async function submitFeedbackAPI(workflowId, feedback) {
    return fetchAPI(`/submit_feedback/${workflowId}`, {
        method: 'POST',
        body: JSON.stringify({ feedback }),
    });
}

// ============================================================================
// UI Functions
// ============================================================================

function renderWorkflowList() {
    const container = document.getElementById('workflow-list');

    if (workflows.length === 0) {
        container.innerHTML = '<div class="loading">No workflows yet</div>';
        return;
    }

    container.innerHTML = workflows.map(workflow => `
        <div class="workflow-item ${workflow.workflow_id === currentWorkflowId ? 'active' : ''}"
             onclick="selectWorkflow('${workflow.workflow_id}')">
            <div class="workflow-item-title">${escapeHtml(workflow.refactoring_goal)}</div>
            <div class="workflow-item-status">${workflow.status}</div>
        </div>
    `).join('');
}

function updateStats() {
    document.getElementById('stat-total').textContent = workflows.length;
    document.getElementById('stat-pending').textContent =
        workflows.filter(w => w.status === 'AWAITING_REVIEW').length;
    document.getElementById('stat-completed').textContent =
        workflows.filter(w => w.status === 'COMPLETED').length;
}

function selectWorkflow(workflowId) {
    currentWorkflowId = workflowId;

    // Hide welcome screen, show detail
    document.getElementById('welcome-screen').classList.add('hidden');
    document.getElementById('workflow-detail').classList.remove('hidden');

    // Update active state in list
    renderWorkflowList();

    // Load workflow details
    loadWorkflowDetail(workflowId);

    // Start polling for updates
    startPolling(workflowId);
}

async function loadWorkflowDetail(workflowId) {
    try {
        const status = await getWorkflowStatus(workflowId);
        renderWorkflowDetail(status);
    } catch (error) {
        console.error('Failed to load workflow detail:', error);
        showToast('Failed to load workflow details', 'error');
    }
}

function renderWorkflowDetail(status) {
    // Update header
    document.getElementById('detail-goal').textContent = status.refactoring_goal;

    const statusBadge = document.getElementById('detail-status');
    statusBadge.textContent = status.status;
    statusBadge.className = `status-badge ${status.status.toLowerCase()}`;

    // Update progress
    const maxIterations = 3;  // Default
    const progress = Math.min((status.iteration_count / maxIterations) * 100, 100);
    document.getElementById('progress-fill').style.width = `${progress}%`;
    document.getElementById('progress-text').textContent =
        `Iteration ${status.iteration_count} of ${maxIterations}`;
    document.getElementById('progress-file').textContent =
        status.current_file || 'Processing...';

    // Update diff viewer
    const diffContent = status.current_diff || 'No changes to display';
    document.querySelector('.diff-content').textContent = diffContent;

    // Update summary
    const summaryContent = status.refactoring_summary || 'Waiting for agent explanation...';
    document.getElementById('summary-content').textContent = summaryContent;

    // Update validation results
    renderValidationResults(status.validation_results);

    // Show/hide action buttons based on status
    const actionSection = document.querySelector('.action-section');
    if (status.status === 'AWAITING_REVIEW') {
        actionSection.classList.remove('hidden');
    } else {
        actionSection.classList.add('hidden');
    }

    // Display error message if present
    const errorContainer = document.getElementById('error-container') || createErrorContainer();
    if (status.status === 'ERROR' && status.error_message) {
        errorContainer.textContent = `Error: ${status.error_message}`;
        errorContainer.classList.remove('hidden');
    } else {
        errorContainer.classList.add('hidden');
    }
}

function createErrorContainer() {
    const container = document.createElement('div');
    container.id = 'error-container';
    container.className = 'error-banner hidden';

    // Insert after header
    const header = document.querySelector('.detail-header');
    header.parentNode.insertBefore(container, header.nextSibling);

    return container;
}

function renderValidationResults(results) {
    const container = document.getElementById('validation-results');

    if (!results || results.length === 0) {
        container.innerHTML = '<div class="loading">No validation results yet</div>';
        return;
    }

    container.innerHTML = results.map(result => `
        <div class="validation-item ${result.passed ? 'success' : 'failed'}">
            <span class="validation-icon">${result.passed ? '✓' : '✗'}</span>
            <span class="validation-name">${escapeHtml(result.tool_name)}</span>
            <span class="validation-status">${result.passed ? 'Passed' : 'Failed'}</span>
        </div>
    `).join('');
}

// ============================================================================
// Workflow Actions
// ============================================================================

async function startWorkflow() {
    const goal = document.getElementById('refactoring-goal').value.trim();
    const content = document.getElementById('file-content').value;
    const filePath = document.getElementById('file-path').value.trim();
    const maxIterations = parseInt(document.getElementById('max-iterations').value) || 3;

    if (!goal) {
        showToast('Please enter a refactoring goal', 'error');
        return;
    }

    if (!content) {
        showToast('Please enter code to refactor', 'error');
        return;
    }

    const files = { [filePath]: content };

    try {
        showToast('Starting workflow...', 'success');
        hideNewWorkflowModal();

        const workflow = await startWorkflowAPI(goal, files, maxIterations);

        // Add to local state
        workflows.unshift(workflow);
        renderWorkflowList();
        updateStats();

        // Select the new workflow
        selectWorkflow(workflow.workflow_id);

        showToast('Workflow started successfully!', 'success');
    } catch (error) {
        console.error('Failed to start workflow:', error);
        showToast(`Failed to start workflow: ${error.message}`, 'error');
    }
}

async function approveChanges() {
    if (!currentWorkflowId) return;

    try {
        await resumeWorkflowAPI(currentWorkflowId, 'APPROVE');
        showToast('Changes approved!', 'success');
        loadWorkflows();
    } catch (error) {
        showToast(`Failed to approve: ${error.message}`, 'error');
    }
}

async function rejectChanges() {
    if (!currentWorkflowId) return;

    try {
        await resumeWorkflowAPI(currentWorkflowId, 'REJECT');
        showToast('Changes rejected', 'success');
        loadWorkflows();
    } catch (error) {
        showToast(`Failed to reject: ${error.message}`, 'error');
    }
}

async function submitFeedback() {
    const feedback = document.getElementById('feedback-text').value.trim();

    if (!feedback) {
        showToast('Please enter feedback', 'error');
        return;
    }

    if (!currentWorkflowId) return;

    try {
        await submitFeedbackAPI(currentWorkflowId, feedback);
        hideFeedbackModal();
        showToast('Feedback submitted!', 'success');
    } catch (error) {
        showToast(`Failed to submit feedback: ${error.message}`, 'error');
    }
}

// ============================================================================
// Modal Functions
// ============================================================================

function showNewWorkflowModal() {
    document.getElementById('new-workflow-modal').classList.remove('hidden');
}

function hideNewWorkflowModal() {
    document.getElementById('new-workflow-modal').classList.add('hidden');
    // Clear form
    document.getElementById('refactoring-goal').value = '';
    document.getElementById('file-content').value = '';
}

function showFeedbackModal() {
    document.getElementById('feedback-modal').classList.remove('hidden');
}

function hideFeedbackModal() {
    document.getElementById('feedback-modal').classList.add('hidden');
    document.getElementById('feedback-text').value = '';
}

// ============================================================================
// Polling
// ============================================================================

function startPolling(workflowId) {
    // Clear existing interval
    if (pollInterval) {
        clearInterval(pollInterval);
    }

    // Poll every 2 seconds
    pollInterval = setInterval(async () => {
        try {
            const status = await getWorkflowStatus(workflowId);
            renderWorkflowDetail(status);

            // Stop polling if workflow is complete or errored
            if (['COMPLETED', 'ERROR', 'CANCELLED'].includes(status.status)) {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Try to load existing workflows
    loadWorkflows();

    // Poll for new workflows every 5 seconds
    setInterval(loadWorkflows, 5000);

    // Handle modal close on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
            }
        });
    });

    // Handle escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.classList.add('hidden');
            });
        }
    });
});
