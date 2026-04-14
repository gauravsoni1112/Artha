"""
Integration tests for agent chat — real DB, mocked LLM.

Requires Docker + running Postgres. Tests chat persistence to chat_sessions and agent_runs tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from langchain_core.messages import AIMessage
from libs.schemas.db_models import AgentRun, Base, ChatSession, Owner
from services.agent.agent import ArthaAgent
from services.agent.config import LLMConfig


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentChatPersistence:
    """Test chat persistence to database."""

    @pytest_asyncio.fixture
    async def db_session(self):
        """Create isolated test database session with savepoint rollback."""
        engine = create_async_engine(
            "postgresql+asyncpg://artha:artha_secret@localhost:5432/artha",
            echo=False,
        )

        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)

            @event.listens_for(session.sync_session, "after_transaction_end")
            def restart_savepoint(db_session, transaction):
                if transaction.nested and not transaction._parent.nested:
                    session.sync_session.begin_nested()

            await conn.begin_nested()

            yield session

            await session.close()
            await trans.rollback()

        await engine.dispose()

    @pytest_asyncio.fixture
    async def test_owner(self, db_session):
        """Create a test owner."""
        owner = Owner(name="Test Owner")
        db_session.add(owner)
        await db_session.flush()
        return owner

    async def test_chat_creates_chat_session(self, db_session, test_owner):
        """chat() without session_id creates a new ChatSession."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_llm.invoke = Mock(
                return_value=AIMessage(content="Your balance is ₹10,000")
            )
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)
            result = await agent.chat(
                owner_id=str(test_owner.id),
                message="What is my balance?",
            )

        # Verify session was created
        sessions = await db_session.scalars(
            select(ChatSession).where(ChatSession.owner_id == test_owner.id)
        )
        sessions_list = sessions.all()
        assert len(sessions_list) == 1
        assert sessions_list[0].title == "What is my balance?"[:80]
        assert sessions_list[0].status == "ACTIVE"

        # Verify result contains session_id
        assert "session_id" in result
        assert result["session_id"] == str(sessions_list[0].id)

    async def test_chat_creates_agent_run(self, db_session, test_owner):
        """chat() creates an AgentRun record linked to ChatSession."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_msg = AIMessage(content="You spent ₹500")
            mock_llm.invoke = Mock(return_value=mock_msg)
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)
            result = await agent.chat(
                owner_id=str(test_owner.id),
                message="Total spend?",
            )

        # Verify AgentRun was created
        runs = await db_session.scalars(
            select(AgentRun).where(AgentRun.owner_id == test_owner.id)
        )
        runs_list = runs.all()
        assert len(runs_list) == 1

        run = runs_list[0]
        assert run.user_message == "Total spend?"
        assert run.assistant_response == "You spent ₹500"
        assert run.status == "OK"
        assert run.error_message is None
        assert run.completed_at is not None
        assert run.turn_index == 0

        # Verify result contains run_id
        assert "run_id" in result
        assert result["run_id"] == str(run.id)

    async def test_chat_continuation_with_session_id(self, db_session, test_owner):
        """Passing session_id continues conversation in same session."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_llm.invoke = Mock(
                side_effect=[
                    AIMessage(content="First response"),
                    AIMessage(content="Second response"),
                ]
            )
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)

            # First message (creates session)
            result1 = await agent.chat(
                owner_id=str(test_owner.id),
                message="First question",
            )
            session_id = result1["session_id"]

            # Second message (uses existing session)
            result2 = await agent.chat(
                owner_id=str(test_owner.id),
                message="Follow-up question",
                session_id=session_id,
            )

        # Verify both turns are in same session
        assert result2["session_id"] == session_id

        # Verify turn_index incremented
        runs = await db_session.scalars(
            select(AgentRun)
            .where(AgentRun.session_id == uuid.UUID(session_id))
            .order_by(AgentRun.turn_index)
        )
        runs_list = runs.all()
        assert len(runs_list) == 2
        assert runs_list[0].turn_index == 0
        assert runs_list[1].turn_index == 1
        assert runs_list[0].user_message == "First question"
        assert runs_list[1].user_message == "Follow-up question"

    async def test_chat_messages_trace_persisted(self, db_session, test_owner):
        """Full LangGraph message trace is stored in JSONB."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_llm.invoke = Mock(
                return_value=AIMessage(content="Response")
            )
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)
            await agent.chat(owner_id=str(test_owner.id), message="Test")

        # Verify messages_trace is stored
        run = (
            await db_session.scalars(select(AgentRun).where(AgentRun.owner_id == test_owner.id))
        ).first()
        assert run.messages_trace is not None
        assert isinstance(run.messages_trace, list)
        assert len(run.messages_trace) > 0

    async def test_chat_tool_calls_persisted(self, db_session, test_owner):
        """Tool calls list is persisted in JSONB."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_msg = AIMessage(
                content="Here's your data",
                tool_calls=[
                    {"name": "transaction_query", "args": {}, "id": "call_1"},
                    {"name": "net_worth", "args": {}, "id": "call_2"},
                ],
            )
            mock_llm.invoke = Mock(return_value=mock_msg)
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)
            await agent.chat(owner_id=str(test_owner.id), message="Financial summary")

        run = (
            await db_session.scalars(select(AgentRun).where(AgentRun.owner_id == test_owner.id))
        ).first()
        assert run.tool_calls == ["transaction_query", "net_worth"]

    async def test_chat_session_timestamps(self, db_session, test_owner):
        """Session created_at and updated_at are set automatically."""
        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_llm.invoke = Mock(
                return_value=AIMessage(content="Response")
            )
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)
            await agent.chat(owner_id=str(test_owner.id), message="Test")

        session = (
            await db_session.scalars(select(ChatSession).where(ChatSession.owner_id == test_owner.id))
        ).first()
        assert session.created_at is not None
        assert session.updated_at is not None
        # Verify timestamp is recent (within 10 seconds to account for clock skew)
        now = datetime.now(timezone.utc)
        created = session.created_at if session.created_at.tzinfo else session.created_at.replace(tzinfo=timezone.utc)
        assert (now - created).total_seconds() < 10

    async def test_nonexistent_session_raises_error(self, db_session, test_owner):
        """Passing invalid session_id raises ValueError."""
        fake_session_id = str(uuid.uuid4())

        with patch.object(LLMConfig, "build_chat_model") as mock_build_model:
            mock_llm = Mock()
            mock_llm.bind_tools = Mock(return_value=mock_llm)
            mock_llm.invoke = Mock(
                return_value=AIMessage(content="Response")
            )
            mock_build_model.return_value = mock_llm

            agent = ArthaAgent(session=db_session)

            with pytest.raises(ValueError, match="Session .* not found"):
                await agent.chat(
                    owner_id=str(test_owner.id),
                    message="Test",
                    session_id=fake_session_id,
                )
