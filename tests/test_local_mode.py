# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

"""Tests — cohérence du mode local (Ollama) hors-ligne."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Never
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.engine.agent import Agent
from jarvis.engine.background.notifications import NotificationQueue
from jarvis.engine.background.worker import BackgroundWorker
from jarvis.engine.gateway import Gateway
from jarvis.engine.session import SessionManager
from jarvis.providers.llm.api import AnthropicProvider
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.llm.local import OllamaProvider
from jarvis.providers.memory.consolidation import CrossSessionRecall

# ── Fixtures de mode ──────────────────────────────────────────────────────────


@pytest.fixture
def local_mode() -> Iterator[None]:
    from jarvis.kernel.settings import settings

    old = settings.llm_provider
    object.__setattr__(settings, "llm_provider", "local")
    yield
    object.__setattr__(settings, "llm_provider", old)


@pytest.fixture
def api_mode() -> Iterator[None]:
    from jarvis.kernel.settings import settings

    old = settings.llm_provider
    object.__setattr__(settings, "llm_provider", "api")
    yield
    object.__setattr__(settings, "llm_provider", old)


# ── LLM factice ───────────────────────────────────────────────────────────────


class _MockLLM(LLMProvider):
    """Provider factice — retourne une réponse fixe sans réseau."""

    def __init__(self, response: str = "[I] ok") -> None:
        self._response = response
        self._model = "mock-model"

    async def complete(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs: object,
    ) -> str | AsyncIterator[str]:
        if stream:
            return self._stream()
        return self._response

    async def _stream(self) -> AsyncIterator[str]:
        for word in self._response.split():
            yield word + " "

    async def health_check(self) -> bool:
        return True


def test_local_mode_uses_a_compact_holmes_prompt(local_mode: None) -> None:
    from jarvis.kernel.settings import settings

    agent = Agent(settings=settings, llm=_MockLLM())
    system = agent._build_system(
        recall_summary="# Body\n\nLa note source inventorie 15 CT distincts."
    )

    assert "Tu es Holmes" in system
    assert "15 CT distincts" in system
    assert "Fusion 360" not in system
    assert "Mémoire à 3 couches" not in system
    assert len(system) < 6_000


def test_ha_conversation_uses_a_small_stable_prompt(local_mode: None) -> None:
    from jarvis.kernel.settings import settings

    agent = Agent(settings=settings, llm=_MockLLM())
    first = agent._build_system(recall_summary="contexte A", ha_conversation=True)
    second = agent._build_system(recall_summary="contexte B", ha_conversation=True)

    assert "conversation Home Assistant" in first
    assert len(first) < 2_000
    assert (
        first.split("=== CONTEXTE DYNAMIQUE ===", 1)[0]
        == second.split("=== CONTEXTE DYNAMIQUE ===", 1)[0]
    )


def test_ha_conversation_excludes_long_user_profile_files(local_mode: None, tmp_path: Path) -> None:
    from jarvis.kernel.settings import settings

    profile = tmp_path / "profile.md"
    preferences = tmp_path / "preferences.md"
    profile.write_text("PROFIL_TRÈS_LONG " * 500)
    preferences.write_text("PRÉFÉRENCES_TRÈS_LONGUES " * 500)
    agent = Agent(
        settings=settings,
        llm=_MockLLM(),
        user_model_path=profile,
        user_prefs_path=preferences,
    )

    system = agent._build_system(ha_conversation=True)

    assert "PROFIL_TRÈS_LONG" not in system
    assert "PRÉFÉRENCES_TRÈS_LONGUES" not in system
    assert len(system) < 2_000


def test_local_voice_profile_never_promises_persistent_memory(local_mode: None) -> None:
    from jarvis.kernel.settings import settings

    system = Agent(settings=settings, llm=_MockLLM())._build_system()

    assert "ne promets jamais de mémoriser" in system.lower()
    assert "pendant la conversation en cours" in system.lower()


def test_local_prompt_assigns_memory_present_and_general_knowledge_sources(
    local_mode: None,
) -> None:
    from jarvis.kernel.settings import settings

    system = Agent(settings=settings, llm=_MockLLM())._build_system()

    assert "Soul pour les souvenirs" in system
    assert "Home Assistant pour le\nprésent" in system
    assert "connaissances générales pour le reste" in system
    assert "N'invente jamais" in system
    assert "état actuel\nn'est pas disponible" in system


def test_local_prompt_distinguishes_current_conversation_soul_and_ha(
    local_mode: None,
) -> None:
    from jarvis.kernel.settings import settings

    system = Agent(settings=settings, llm=_MockLLM())._build_system(
        recall_summary="## Mémoire Soul\nfait durable\n\n## Contexte ambiant\nfait présent"
    )

    assert "tu m'as\n  dit que" in system
    assert "ne l'appelle jamais une\n  mémoire Soul" in system
    assert "## Sources contextuelles externes" in system
    assert "Mémoire Soul et Home Assistant ne sont pas interchangeables" in system
    assert "## Mémoire pertinente" not in system


def test_api_voice_profile_never_promises_persistent_memory(api_mode: None) -> None:
    from jarvis.kernel.settings import settings

    system = Agent(settings=settings, llm=_MockLLM())._build_system()

    assert "ne promets jamais de mémoriser" in system.lower()
    assert "pendant la conversation en cours" in system.lower()
    assert "tu veux que je mémorise ça" not in system.lower()


# ── Test 1 : is_offline_mode ──────────────────────────────────────────────────


def test_offline_mode_when_local(local_mode: None) -> None:
    """is_offline_mode() est True quand llm_provider == 'local'."""
    from jarvis.kernel.connectivity import is_offline_mode

    assert is_offline_mode() is True


def test_online_mode_when_api(api_mode: None) -> None:
    """is_offline_mode() est False quand llm_provider == 'api'."""
    from jarvis.kernel.connectivity import is_offline_mode

    assert is_offline_mode() is False


# ── Test 2 : factory retourne OllamaProvider en mode local ───────────────────


def test_gateway_uses_ollama_in_local_mode(local_mode: None) -> None:
    """En mode local, get_llm_provider() doit retourner OllamaProvider."""
    from jarvis.providers.llm.factory import get_llm_provider

    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider), (
        f"Mode local doit instancier OllamaProvider, got {type(provider).__name__}"
    )
    assert not isinstance(provider, AnthropicProvider)


def test_background_llm_not_anthropic_in_local_mode(local_mode: None) -> None:
    """create_background_llm() ne renvoie pas AnthropicProvider en mode local."""
    from jarvis.providers.llm.factory import create_background_llm

    bg_llm = create_background_llm()
    assert not isinstance(bg_llm, AnthropicProvider)
    assert isinstance(bg_llm, OllamaProvider)


# ── Test 3 : hot-swap met à jour gateway + voice_gateway ─────────────────────


def test_hot_swap_updates_gateway_and_voice_gateway(local_mode: None) -> None:
    """Après hot-swap en mode local, gateway ET voice_gateway utilisent OllamaProvider."""
    anthropic_llm = _MockLLM()

    from jarvis.kernel.settings import settings as _settings

    agent_main = Agent(settings=_settings, llm=anthropic_llm)
    agent_voice = Agent(settings=_settings, llm=anthropic_llm)
    notifications = NotificationQueue()
    worker = BackgroundWorker(llm=anthropic_llm, notifications=notifications)
    mgr = SessionManager()

    gw = Gateway(session_manager=mgr, agent=agent_main, notifications=notifications, worker=worker)
    vgw = Gateway(
        session_manager=mgr, agent=agent_voice, notifications=notifications, worker=worker
    )

    # Simule le hot-swap (même logique que http_config.update_setting)
    from jarvis.providers.llm.factory import get_llm_provider

    new_llm = get_llm_provider()
    object.__setattr__(gw._agent, "_llm", new_llm)
    object.__setattr__(vgw._agent, "_llm", new_llm)
    object.__setattr__(worker, "_llm", new_llm)

    assert isinstance(gw._agent._llm, OllamaProvider), "gateway doit utiliser OllamaProvider"
    assert isinstance(vgw._agent._llm, OllamaProvider), "voice_gateway doit utiliser OllamaProvider"
    assert isinstance(worker._llm, OllamaProvider), "worker doit utiliser OllamaProvider"
    assert not isinstance(gw._agent._llm, AnthropicProvider)
    assert not isinstance(vgw._agent._llm, AnthropicProvider)


# ── Test 4 : CrossSessionRecall skip résumé LLM en mode offline ───────────────


@pytest.mark.asyncio
async def test_cross_session_recall_offline_skips_llm(local_mode: None) -> None:
    """CrossSessionRecall.recall() en mode local ne fait pas d'appel LLM."""
    mock_llm = _MockLLM()
    mock_llm.complete = AsyncMock(return_value="résumé LLM")

    fts_mock = MagicMock()
    fts_mock.search = AsyncMock(
        return_value=[{"doc_id": "s1", "text": "Barth aime l'électronique"}]
    )
    vec_mock = MagicMock()
    vec_mock.search = AsyncMock(return_value=[])

    recall = CrossSessionRecall(llm=mock_llm, fts_index=fts_mock, vector_index=vec_mock)
    result = await recall.recall("électronique")

    mock_llm.complete.assert_not_called()
    assert result is not None
    assert "Barth" in result


@pytest.mark.asyncio
async def test_cross_session_recall_online_calls_llm(api_mode: None) -> None:
    """CrossSessionRecall.recall() en mode api appelle bien le LLM pour le résumé."""
    mock_llm = _MockLLM()
    mock_llm.complete = AsyncMock(return_value="résumé produit par le LLM")

    fts_mock = MagicMock()
    fts_mock.search = AsyncMock(
        return_value=[{"doc_id": "s1", "text": "Barth aime l'électronique"}]
    )
    vec_mock = MagicMock()
    vec_mock.search = AsyncMock(return_value=[])

    recall = CrossSessionRecall(llm=mock_llm, fts_index=fts_mock, vector_index=vec_mock)
    result = await recall.recall("électronique")

    mock_llm.complete.assert_called_once()
    assert result == "résumé produit par le LLM"


# ── Test 5 : CollectorBase en mode offline → [] sans ERROR ────────────────────


@pytest.mark.asyncio
async def test_collector_base_offline_no_error_log(
    local_mode: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """En mode local, une exception dans _collect() produit un DEBUG, pas un ERROR."""
    from jarvis.engine.proactive.collectors.base import CollectorBase

    class _FailingCollector(CollectorBase):
        name = "test_failing"

        async def _collect(self) -> Never:
            raise ConnectionRefusedError("réseau inaccessible")

    import logging

    with caplog.at_level(logging.DEBUG):
        items = await _FailingCollector().collect()

    assert items == []
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_records, (
        f"Des ERROR inattendus en mode local : {[r.message for r in error_records]}"
    )


@pytest.mark.asyncio
async def test_collector_base_online_returns_empty_on_failure(api_mode: None) -> None:
    """En mode api, une exception dans _collect() retourne [] sans lever."""
    from jarvis.engine.proactive.collectors.base import CollectorBase

    class _FailingCollector(CollectorBase):
        name = "test_failing_online"

        async def _collect(self) -> Never:
            raise ConnectionRefusedError("réseau inaccessible")

    # CollectorBase.collect() doit absorber l'exception et retourner [] dans tous les cas
    items = await _FailingCollector().collect()
    assert items == []
