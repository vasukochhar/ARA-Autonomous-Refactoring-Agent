"""
PostgreSQL persistence layer for ARA.

Provides database connection management and LangGraph checkpointer
configuration for long-running, interruptible workflows.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from pydantic import BaseModel, Field

from ara.config import get_settings

logger = structlog.get_logger()


class DatabaseConfig(BaseModel):
    """Database configuration."""

    url: str = Field(..., description="PostgreSQL connection URL")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")


async def get_async_connection():
    """
    Get an async database connection.

    Returns an asyncpg connection for direct database operations.
    """
    try:
        import asyncpg

        settings = get_settings()
        conn = await asyncpg.connect(settings.database_url)
        logger.info("database_connected", url=settings.database_url.split("@")[-1])
        return conn
    except ImportError:
        logger.error("asyncpg_not_installed")
        raise ImportError("asyncpg is required for async database operations")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        raise


@asynccontextmanager
async def get_async_connection_context() -> AsyncGenerator:
    """
    Async context manager for database connections.

    Usage:
        async with get_async_connection_context() as conn:
            await conn.execute("SELECT 1")
    """
    conn = await get_async_connection()
    try:
        yield conn
    finally:
        await conn.close()
        logger.debug("database_connection_closed")


async def init_database_schema(conn) -> None:
    """
    Initialize the database schema for ARA.

    Creates the necessary tables for workflow state persistence.
    """
    schema_sql = """
    -- Workflow metadata table
    CREATE TABLE IF NOT EXISTS ara_workflows (
        workflow_id UUID PRIMARY KEY,
        refactoring_goal TEXT NOT NULL,
        status VARCHAR(20) DEFAULT 'PENDING',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        completed_at TIMESTAMP WITH TIME ZONE,
        error_message TEXT
    );

    -- File contexts for each workflow
    CREATE TABLE IF NOT EXISTS ara_file_contexts (
        id SERIAL PRIMARY KEY,
        workflow_id UUID REFERENCES ara_workflows(workflow_id) ON DELETE CASCADE,
        filepath TEXT NOT NULL,
        original_content TEXT,
        modified_content TEXT,
        diff TEXT,
        status VARCHAR(20) DEFAULT 'PENDING',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(workflow_id, filepath)
    );

    -- Validation results history
    CREATE TABLE IF NOT EXISTS ara_validation_results (
        id SERIAL PRIMARY KEY,
        workflow_id UUID REFERENCES ara_workflows(workflow_id) ON DELETE CASCADE,
        tool_name VARCHAR(50) NOT NULL,
        passed BOOLEAN NOT NULL,
        error_message TEXT,
        stdout TEXT,
        stderr TEXT,
        exit_code INTEGER,
        execution_time_ms INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Reflection notes
    CREATE TABLE IF NOT EXISTS ara_reflections (
        id SERIAL PRIMARY KEY,
        workflow_id UUID REFERENCES ara_workflows(workflow_id) ON DELETE CASCADE,
        iteration INTEGER NOT NULL,
        error_summary TEXT,
        suggested_fix TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Create indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_workflows_status ON ara_workflows(status);
    CREATE INDEX IF NOT EXISTS idx_file_contexts_workflow ON ara_file_contexts(workflow_id);
    CREATE INDEX IF NOT EXISTS idx_validation_workflow ON ara_validation_results(workflow_id);
    
    -- State checkpoints for time-travel debugging
    CREATE TABLE IF NOT EXISTS ara_checkpoints (
        id SERIAL PRIMARY KEY,
        workflow_id UUID REFERENCES ara_workflows(workflow_id) ON DELETE CASCADE,
        checkpoint_id VARCHAR(100) NOT NULL,
        step_number INTEGER NOT NULL,
        node_name VARCHAR(100),
        state_json JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(workflow_id, checkpoint_id)
    );
    
    CREATE INDEX IF NOT EXISTS idx_checkpoints_workflow ON ara_checkpoints(workflow_id);
    CREATE INDEX IF NOT EXISTS idx_checkpoints_step ON ara_checkpoints(workflow_id, step_number);
    """

    await conn.execute(schema_sql)
    logger.info("database_schema_initialized")


async def get_langgraph_checkpointer():
    """
    Get a LangGraph checkpointer configured for PostgreSQL.

    This enables persistent state storage for long-running workflows,
    allowing the agent to be interrupted and resumed.

    Returns:
        AsyncPostgresSaver instance configured for the database.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        settings = get_settings()
        checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url)

        logger.info("langgraph_checkpointer_created")
        return checkpointer

    except ImportError:
        logger.warning(
            "langgraph_postgres_not_available",
            message="Using in-memory checkpointer instead",
        )
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


class WorkflowRepository:
    """
    Repository for workflow CRUD operations.

    Provides methods to create, read, update, and delete workflows
    in the PostgreSQL database.
    """

    def __init__(self, conn):
        self.conn = conn

    async def create_workflow(
        self, workflow_id: str, refactoring_goal: str
    ) -> dict:
        """Create a new workflow record."""
        result = await self.conn.fetchrow(
            """
            INSERT INTO ara_workflows (workflow_id, refactoring_goal)
            VALUES ($1, $2)
            RETURNING workflow_id, refactoring_goal, status, created_at
            """,
            workflow_id,
            refactoring_goal,
        )
        logger.info("workflow_created", workflow_id=workflow_id)
        return dict(result)

    async def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """Get a workflow by ID."""
        result = await self.conn.fetchrow(
            "SELECT * FROM ara_workflows WHERE workflow_id = $1",
            workflow_id,
        )
        return dict(result) if result else None

    async def update_workflow_status(
        self, workflow_id: str, status: str, error_message: str = None
    ) -> None:
        """Update workflow status."""
        await self.conn.execute(
            """
            UPDATE ara_workflows 
            SET status = $2, error_message = $3, updated_at = NOW()
            WHERE workflow_id = $1
            """,
            workflow_id,
            status,
            error_message,
        )
        logger.info("workflow_status_updated", workflow_id=workflow_id, status=status)

    async def list_workflows(
        self, status: str = None, limit: int = 50
    ) -> list:
        """List workflows, optionally filtered by status."""
        if status:
            results = await self.conn.fetch(
                """
                SELECT * FROM ara_workflows 
                WHERE status = $1 
                ORDER BY created_at DESC 
                LIMIT $2
                """,
                status,
                limit,
            )
        else:
            results = await self.conn.fetch(
                "SELECT * FROM ara_workflows ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [dict(r) for r in results]


class CheckpointRepository:
    """
    Repository for checkpoint CRUD operations.
    
    Enables time-travel debugging by saving and restoring
    workflow state at any step.
    """
    
    def __init__(self, conn):
        self.conn = conn
    
    async def save_checkpoint(
        self,
        workflow_id: str,
        checkpoint_id: str,
        step_number: int,
        node_name: str,
        state: dict,
    ) -> dict:
        """
        Save a checkpoint of the workflow state.
        
        Args:
            workflow_id: The workflow UUID
            checkpoint_id: Unique checkpoint identifier
            step_number: Step number in the workflow
            node_name: Name of the current node
            state: Full workflow state to save
        
        Returns:
            Saved checkpoint record
        """
        import json
        
        # Serialize state to JSON (handle non-serializable objects)
        state_json = self._serialize_state(state)
        
        result = await self.conn.fetchrow(
            """
            INSERT INTO ara_checkpoints (workflow_id, checkpoint_id, step_number, node_name, state_json)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (workflow_id, checkpoint_id) DO UPDATE
            SET step_number = $3, node_name = $4, state_json = $5, created_at = NOW()
            RETURNING id, workflow_id, checkpoint_id, step_number, node_name, created_at
            """,
            workflow_id,
            checkpoint_id,
            step_number,
            node_name,
            state_json,
        )
        logger.info("checkpoint_saved", workflow_id=workflow_id, step=step_number, node=node_name)
        return dict(result)
    
    async def load_checkpoint(
        self, workflow_id: str, checkpoint_id: str
    ) -> Optional[dict]:
        """
        Load a specific checkpoint.
        
        Args:
            workflow_id: The workflow UUID
            checkpoint_id: Checkpoint to load
        
        Returns:
            Deserialized state or None
        """
        result = await self.conn.fetchrow(
            """
            SELECT state_json FROM ara_checkpoints
            WHERE workflow_id = $1 AND checkpoint_id = $2
            """,
            workflow_id,
            checkpoint_id,
        )
        if result:
            return self._deserialize_state(result["state_json"])
        return None
    
    async def list_checkpoints(self, workflow_id: str) -> list:
        """
        List all checkpoints for a workflow.
        
        Returns checkpoints in step order for time-travel navigation.
        """
        results = await self.conn.fetch(
            """
            SELECT id, checkpoint_id, step_number, node_name, created_at
            FROM ara_checkpoints
            WHERE workflow_id = $1
            ORDER BY step_number ASC
            """,
            workflow_id,
        )
        return [dict(r) for r in results]
    
    async def rewind_to_step(self, workflow_id: str, step_number: int) -> Optional[dict]:
        """
        Rewind workflow to a specific step.
        
        Returns the state at that step, enabling time-travel debugging.
        
        Args:
            workflow_id: The workflow UUID
            step_number: Step to rewind to
        
        Returns:
            State at that step or None if not found
        """
        result = await self.conn.fetchrow(
            """
            SELECT state_json FROM ara_checkpoints
            WHERE workflow_id = $1 AND step_number = $2
            """,
            workflow_id,
            step_number,
        )
        if result:
            logger.info("checkpoint_rewound", workflow_id=workflow_id, step=step_number)
            return self._deserialize_state(result["state_json"])
        return None
    
    async def delete_after_step(self, workflow_id: str, step_number: int) -> int:
        """
        Delete all checkpoints after a given step.
        
        Used when rewinding and then making new edits.
        
        Returns:
            Number of checkpoints deleted
        """
        result = await self.conn.execute(
            """
            DELETE FROM ara_checkpoints
            WHERE workflow_id = $1 AND step_number > $2
            """,
            workflow_id,
            step_number,
        )
        # Parse "DELETE N" response
        count = int(result.split()[-1]) if result else 0
        logger.info("checkpoints_deleted", workflow_id=workflow_id, after_step=step_number, count=count)
        return count
    
    def _serialize_state(self, state: dict) -> str:
        """Serialize state to JSON string."""
        import json
        
        def default_serializer(obj):
            # Handle Pydantic models
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            # Handle enums
            if hasattr(obj, "value"):
                return obj.value
            # Handle datetime
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)
        
        return json.dumps(state, default=default_serializer)
    
    def _deserialize_state(self, state_json: str) -> dict:
        """Deserialize state from JSON string."""
        import json
        return json.loads(state_json) if isinstance(state_json, str) else dict(state_json)

