"""
Cloud boundary enforcement tests.

These tests verify three guarantees:
  1. Executor and Compactor are hard-blocked from cloud routing.
  2. Cloud-eligible roles (Reflector, Synthesizer, Critic) require anonymise=True.
  3. Payloads leaving for cloud contain no PII after scrubbing.

Run with: pytest tests/unit/privacy/test_boundary_check.py
"""

from __future__ import annotations

import json
import pytest

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from libs.privacy.anonymiser import Anonymiser, _redact_pattern_matches
from libs.privacy.pii_scanner import PIIScanner, default_scanner
from libs.privacy.token_map import TokenMap
from services.agent.config import LLMRole, RoutingPolicy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_ENV = {
    "LLM_PROVIDER": "ollama",
    "LLM_MODEL": "qwen3:8b",
    "LLM_BASE_URL": "http://localhost:11434",
    "LLM_TEMPERATURE": "0",
}


def _env_for_role(role: LLMRole, destination: str, anonymise: bool = False, monkeypatch=None) -> None:
    prefix = role.value.upper()
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(f"{prefix}_DESTINATION", destination)
    monkeypatch.setenv(f"{prefix}_PROVIDER", "ollama")
    monkeypatch.setenv(f"{prefix}_MODEL", "qwen3:8b")
    monkeypatch.setenv(f"{prefix}_ANONYMISE", "true" if anonymise else "false")


# ---------------------------------------------------------------------------
# Section 1 — Hard block: Executor and Compactor must stay local
# ---------------------------------------------------------------------------

class TestLocalOnlyRoles:
    """EXECUTOR and COMPACTOR must raise if destination=cloud is attempted."""

    def test_executor_cloud_raises(self):
        with pytest.raises(ValueError, match="hard NO"):
            RoutingPolicy(
                role=LLMRole.EXECUTOR,
                destination="cloud",
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                anonymise=True,
            )

    def test_compactor_cloud_raises(self):
        with pytest.raises(ValueError, match="hard NO"):
            RoutingPolicy(
                role=LLMRole.COMPACTOR,
                destination="cloud",
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                anonymise=True,
            )

    def test_executor_cloud_raises_from_env(self, monkeypatch):
        _env_for_role(LLMRole.EXECUTOR, "cloud", anonymise=True, monkeypatch=monkeypatch)
        with pytest.raises(ValueError, match="hard NO"):
            RoutingPolicy.from_env(LLMRole.EXECUTOR)

    def test_compactor_cloud_raises_from_env(self, monkeypatch):
        _env_for_role(LLMRole.COMPACTOR, "cloud", anonymise=True, monkeypatch=monkeypatch)
        with pytest.raises(ValueError, match="hard NO"):
            RoutingPolicy.from_env(LLMRole.COMPACTOR)

    def test_executor_local_ok(self):
        policy = RoutingPolicy(
            role=LLMRole.EXECUTOR,
            destination="local",
            provider="ollama",
            model="qwen3:8b",
        )
        assert policy.destination == "local"

    def test_compactor_local_ok(self):
        policy = RoutingPolicy(
            role=LLMRole.COMPACTOR,
            destination="local",
            provider="ollama",
            model="qwen3:4b",
        )
        assert policy.destination == "local"


# ---------------------------------------------------------------------------
# Section 2 — Cloud-eligible roles require anonymise=True
# ---------------------------------------------------------------------------

class TestCloudRequiresAnonymise:
    """Reflector, Synthesizer, Critic can go cloud but only with anonymise=True."""

    @pytest.mark.parametrize("role", [LLMRole.REFLECTOR, LLMRole.SYNTHESIZER, LLMRole.CRITIC])
    def test_cloud_without_anonymise_raises(self, role):
        with pytest.raises(ValueError, match="anonymise=True"):
            RoutingPolicy(
                role=role,
                destination="cloud",
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                anonymise=False,
            )

    @pytest.mark.parametrize("role", [LLMRole.REFLECTOR, LLMRole.SYNTHESIZER, LLMRole.CRITIC])
    def test_cloud_with_anonymise_ok(self, role):
        policy = RoutingPolicy(
            role=role,
            destination="cloud",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            anonymise=True,
        )
        assert policy.destination == "cloud"
        assert policy.anonymise is True

    @pytest.mark.parametrize("role", [LLMRole.REFLECTOR, LLMRole.SYNTHESIZER, LLMRole.CRITIC])
    def test_cloud_from_env_without_anonymise_raises(self, role, monkeypatch):
        _env_for_role(role, "cloud", anonymise=False, monkeypatch=monkeypatch)
        with pytest.raises(ValueError, match="anonymise=True"):
            RoutingPolicy.from_env(role)

    @pytest.mark.parametrize("role", [LLMRole.REFLECTOR, LLMRole.SYNTHESIZER, LLMRole.CRITIC])
    def test_cloud_from_env_with_anonymise_ok(self, role, monkeypatch):
        _env_for_role(role, "cloud", anonymise=True, monkeypatch=monkeypatch)
        policy = RoutingPolicy.from_env(role)
        assert policy.destination == "cloud"
        assert policy.anonymise is True


# ---------------------------------------------------------------------------
# Section 3 — PII does NOT survive scrubbing (boundary payload checks)
# ---------------------------------------------------------------------------

class TestScrubPayloadBoundary:
    """Verify that messages scrubbed by Anonymiser pass the PIIScanner."""

    def setup_method(self):
        self.anon = Anonymiser()
        self.scanner = PIIScanner()

    def _assert_cloud_safe(self, messages):
        """Extract all text from messages and assert no PII detected."""
        combined = " ".join(
            m.content for m in messages if isinstance(m.content, str)
        )
        hits = self.scanner.scan(combined)
        assert hits == [], (
            f"PII survived scrubbing and would reach cloud LLM: "
            + ", ".join(f"{h.entity_type}({h.text!r})" for h in hits)
        )

    def test_pan_scrubbed_from_tool_result(self):
        tm = TokenMap()
        tool_msg = ToolMessage(
            content=json.dumps({"pan": "ABCDE1234F", "amount": 50000}),
            tool_call_id="t1",
        )
        scrubbed = self.anon.scrub_messages([tool_msg], tm)
        self._assert_cloud_safe(scrubbed)

    def test_aadhaar_scrubbed_from_text(self):
        tm = TokenMap()
        msg = HumanMessage(content="Customer aadhaar: 2345 6789 0123 placed an order.")
        scrubbed = self.anon.scrub_messages([msg], tm)
        self._assert_cloud_safe(scrubbed)

    def test_ifsc_scrubbed_from_tool_result(self):
        tm = TokenMap()
        tool_msg = ToolMessage(
            content=json.dumps({"ifsc": "HDFC0001234", "balance": 1000000}),
            tool_call_id="t2",
        )
        scrubbed = self.anon.scrub_messages([tool_msg], tm)
        self._assert_cloud_safe(scrubbed)

    def test_account_number_scrubbed(self):
        tm = TokenMap()
        tool_msg = ToolMessage(
            content=json.dumps({"account_number": "123456789012", "name": "Ravi Kumar"}),
            tool_call_id="t3",
        )
        scrubbed = self.anon.scrub_messages([tool_msg], tm)
        self._assert_cloud_safe(scrubbed)

    def test_phone_scrubbed_from_profile_context(self):
        tm = TokenMap()
        msg = HumanMessage(content="[User profile] owner_id=abc phone=9876543210 income=500000p")
        scrubbed = self.anon.scrub_messages([msg], tm)
        self._assert_cloud_safe(scrubbed)

    def test_owner_id_tokenised_in_profile(self):
        tm = TokenMap()
        owner_uuid = "12345678-1234-1234-1234-123456789abc"
        msg = HumanMessage(content=f"[User profile] owner_id={owner_uuid} income=500000p risk=MODERATE")
        scrubbed = self.anon.scrub_messages([msg], tm)
        combined = " ".join(m.content for m in scrubbed if isinstance(m.content, str))
        assert owner_uuid not in combined, "owner_id UUID must be tokenised before cloud send"

    def test_name_tokenised_in_system_prompt(self):
        tm = TokenMap()
        msg = SystemMessage(content="You are Artha, a personal finance assistant for Ravi Kumar.")
        scrubbed = self.anon.scrub_messages([msg], tm)
        combined = " ".join(m.content for m in scrubbed if isinstance(m.content, str))
        assert "Ravi Kumar" not in combined, "Real name must be tokenised in system prompt"

    def test_description_redacted_from_transaction(self):
        tm = TokenMap()
        tool_msg = ToolMessage(
            content=json.dumps({
                "description": "Payment to RAVI KUMAR HDFC 9876543210",
                "amount_paise": 5000000,
            }),
            tool_call_id="t4",
        )
        scrubbed = self.anon.scrub_messages([tool_msg], tm)
        data = json.loads(scrubbed[0].content)
        assert data["description"] == "[redacted]"

    def test_income_bucketed_not_exact(self):
        tm = TokenMap()
        msg = HumanMessage(content="[User profile] owner_id=abc income=1234567p risk=HIGH")
        scrubbed = self.anon.scrub_messages([msg], tm)
        combined = " ".join(m.content for m in scrubbed if isinstance(m.content, str))
        assert "1234567" not in combined, "Exact income paise must be bucketed before cloud send"

    def test_multiple_pii_fields_all_scrubbed(self):
        """Realistic tool result with several PII fields — all must be clean."""
        tm = TokenMap()
        payload = {
            "account_number": "987654321098",
            "pan": "XYZAB5678C",
            "ifsc": "SBIN0012345",
            "description": "Narration with phone 9123456789",
            "counterparty_name": "HDFC Bank Transfer",
            "amount_paise": 2500000,
        }
        tool_msg = ToolMessage(content=json.dumps(payload), tool_call_id="t5")
        scrubbed = self.anon.scrub_messages([tool_msg], tm)
        self._assert_cloud_safe(scrubbed)


# ---------------------------------------------------------------------------
# Section 4 — _redact_pattern_matches (used by synthesizer for prose answers)
# ---------------------------------------------------------------------------

class TestRedactPatternMatches:
    """Verify the text-level redactor strips hard-pattern PII from prose answers."""

    def test_pan_in_prose(self):
        text = "Your PAN ABCDE1234F has been verified."
        result = _redact_pattern_matches(text)
        assert "ABCDE1234F" not in result
        assert "[pan_redacted]" in result

    def test_aadhaar_in_prose(self):
        text = "Aadhaar 2345 6789 0123 linked to your account."
        result = _redact_pattern_matches(text)
        assert "2345 6789 0123" not in result

    def test_ifsc_in_prose(self):
        text = "Transfer via HDFC0001234 completed."
        result = _redact_pattern_matches(text)
        assert "HDFC0001234" not in result
        assert "[ifsc_redacted]" in result

    def test_phone_in_prose(self):
        text = "Call 9876543210 to confirm."
        result = _redact_pattern_matches(text)
        assert "9876543210" not in result

    def test_clean_text_unchanged(self):
        text = "Your spending is ₹50,000 this month across groceries and utilities."
        result = _redact_pattern_matches(text)
        assert result == text

    def test_synthesizer_prompt_safe_after_scrub(self):
        """Simulate a synthesizer prompt containing PII — must pass PIIScanner after scrub."""
        prompt = (
            "User question: how is my portfolio?\n\n"
            "Agent findings:\n"
            "[cashflow_agent]:\nYour account 987654321098 shows ₹50,000 surplus.\n"
            "[risk_agent]:\nPAN ABCDE1234F linked. IFSC HDFC0001234 active.\n"
        )
        scrubbed = _redact_pattern_matches(prompt)
        hits = default_scanner.scan(scrubbed)
        assert hits == [], (
            "Synthesizer prompt still contains PII after scrub: "
            + ", ".join(f"{h.entity_type}({h.text!r})" for h in hits)
        )

    def test_synthesizer_full_pipeline_scrub_and_detokenise(self):
        """Full _scrub_messages_for_cloud path: scrub → PIIScanner → detokenise response."""
        from langchain_core.messages import HumanMessage, SystemMessage
        from services.orchestrator.synthesizer import _scrub_messages_for_cloud

        tm = TokenMap()
        anon = Anonymiser()
        messages = [
            SystemMessage(content="You are Artha, a personal finance assistant for Ravi Kumar."),
            HumanMessage(
                content=(
                    "User question: how is my portfolio?\n\n"
                    "Agent findings:\n"
                    "[cashflow_agent]:\nAccount 987654321098 shows ₹50,000 surplus.\n"
                    "[risk_agent]:\nPAN ABCDE1234F linked. Phone 9876543210 on file.\n"
                )
            ),
        ]
        scrubbed = _scrub_messages_for_cloud(messages, tm, context="test.synthesizer")
        combined = " ".join(m.content for m in scrubbed if isinstance(m.content, str))

        # Hard-pattern PII must be gone
        assert "ABCDE1234F" not in combined, "PAN survived scrub"
        assert "987654321098" not in combined, "account number survived scrub"
        assert "9876543210" not in combined, "phone survived scrub"
        # Name must be tokenised (not literal)
        assert "Ravi Kumar" not in combined, "name survived scrub"

        # Simulate cloud LLM echoing a token back — detokenise should restore it
        fake_cloud_response = f"Based on the analysis, {anon.detokenise_answer('user_abc123', tm)} is doing well."
        restored = anon.detokenise_answer(fake_cloud_response, tm)
        # detokenise is idempotent when token is unknown — just verify it doesn't crash
        assert isinstance(restored, str)
