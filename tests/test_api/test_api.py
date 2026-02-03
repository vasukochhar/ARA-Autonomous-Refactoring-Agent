"""Tests for API endpoints and workflow management."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from fastapi.testclient import TestClient

from ara.api.main import app
from ara.api.workflow_manager import WorkflowManager, WorkflowInfo


# Create test client
client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_root_returns_healthy(self):
        """Test that root endpoint returns healthy status."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["name"] == "ARA - Autonomous Refactoring Agent"


class TestStartRefactorEndpoint:
    """Tests for the /start_refactor endpoint."""

    @patch("ara.api.main.get_workflow_manager")
    def test_start_refactor_success(self, mock_get_manager):
        """Test starting a refactoring workflow."""
        # Mock the workflow manager
        mock_manager = MagicMock()
        mock_manager.start_workflow = AsyncMock(return_value=WorkflowInfo(
            workflow_id="test-123",
            thread_id="thread_test-123",
            refactoring_goal="Add type hints",
            status="RUNNING",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ))
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/start_refactor", json={
            "refactoring_goal": "Add type hints",
            "files": {"main.py": "def foo(): pass"},
            "max_iterations": 3,
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "test-123"
        assert data["refactoring_goal"] == "Add type hints"

    def test_start_refactor_missing_goal(self):
        """Test that missing goal returns error."""
        response = client.post("/start_refactor", json={
            "files": {"main.py": "def foo(): pass"},
        })
        
        assert response.status_code == 422  # Validation error


class TestGetStatusEndpoint:
    """Tests for the /get_status endpoint."""

    @patch("ara.api.main.get_workflow_manager")
    def test_get_status_found(self, mock_get_manager):
        """Test getting status of existing workflow."""
        mock_manager = MagicMock()
        mock_manager.get_workflow = MagicMock(return_value=WorkflowInfo(
            workflow_id="test-123",
            thread_id="thread_test-123",
            refactoring_goal="Add type hints",
            status="AWAITING_REVIEW",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            current_file="main.py",
            iteration_count=1,
        ))
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/get_status/test-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "test-123"
        assert data["status"] == "AWAITING_REVIEW"

    @patch("ara.api.main.get_workflow_manager")
    def test_get_status_not_found(self, mock_get_manager):
        """Test getting status of non-existent workflow."""
        mock_manager = MagicMock()
        mock_manager.get_workflow = MagicMock(return_value=None)
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/get_status/nonexistent")
        
        assert response.status_code == 404


class TestResumeWorkflowEndpoint:
    """Tests for the /resume_workflow endpoint."""

    @patch("ara.api.main.get_workflow_manager")
    def test_resume_approve(self, mock_get_manager):
        """Test resuming workflow with approve action."""
        mock_manager = MagicMock()
        mock_manager.resume_workflow = AsyncMock(return_value=WorkflowInfo(
            workflow_id="test-123",
            thread_id="thread_test-123",
            refactoring_goal="Add type hints",
            status="COMPLETED",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ))
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/resume_workflow/test-123", json={
            "action": "APPROVE",
            "feedback": "Looks good!",
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"

    def test_resume_invalid_action(self):
        """Test resuming with invalid action."""
        response = client.post("/resume_workflow/test-123", json={
            "action": "INVALID",
        })
        
        assert response.status_code == 422


class TestListWorkflowsEndpoint:
    """Tests for the /workflows endpoint."""

    @patch("ara.api.main.get_workflow_manager")
    def test_list_all_workflows(self, mock_get_manager):
        """Test listing all workflows."""
        now = datetime.now()
        mock_manager = MagicMock()
        mock_manager.list_workflows = MagicMock(return_value=[
            WorkflowInfo(
                workflow_id="test-1",
                thread_id="thread_test-1",
                refactoring_goal="Add type hints",
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            ),
            WorkflowInfo(
                workflow_id="test-2",
                thread_id="thread_test-2",
                refactoring_goal="Rename function",
                status="AWAITING_REVIEW",
                created_at=now,
                updated_at=now,
            ),
        ])
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/workflows")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @patch("ara.api.main.get_workflow_manager")
    def test_list_workflows_filter_by_status(self, mock_get_manager):
        """Test filtering workflows by status."""
        mock_manager = MagicMock()
        mock_manager.list_workflows = MagicMock(return_value=[])
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/workflows?status=COMPLETED")
        
        assert response.status_code == 200
        mock_manager.list_workflows.assert_called_with(status="COMPLETED")


class TestWorkflowManager:
    """Tests for the WorkflowManager class."""

    def test_workflow_manager_init(self):
        """Test WorkflowManager initialization."""
        manager = WorkflowManager(use_persistence=False)
        
        assert manager.use_persistence is False
        assert manager._workflows == {}

    def test_get_nonexistent_workflow(self):
        """Test getting a workflow that doesn't exist."""
        manager = WorkflowManager(use_persistence=False)
        
        result = manager.get_workflow("nonexistent")
        
        assert result is None

    def test_list_empty_workflows(self):
        """Test listing when no workflows exist."""
        manager = WorkflowManager(use_persistence=False)
        
        result = manager.list_workflows()
        
        assert result == []
