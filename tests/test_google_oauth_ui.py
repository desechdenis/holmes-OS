from pathlib import Path

STATIC = Path("src/jarvis/interfaces/ui/static")


def test_oauth_navigation_escapes_the_holmes_page_frame() -> None:
    shared = (STATIC / "_shared.js").read_text()
    assert "Jarvis.beginExternalAuth" in shared
    assert "window.top.location.href = url" in shared


def test_google_connect_buttons_use_top_level_oauth_navigation() -> None:
    settings = (STATIC / "settings.js").read_text()
    capabilities = (STATIC / "capabilities.js").read_text()
    assert "J.beginExternalAuth(c.reconnect_url)" in settings
    assert capabilities.count("J.beginExternalAuth(cfg.url)") == 2


def test_shared_runtime_authenticates_legacy_same_origin_fetches_only() -> None:
    shared = (STATIC / "_shared.js").read_text()

    assert 'target.origin === window.location.origin' in shared
    assert 'target.pathname.startsWith("/api/")' in shared
    assert 'headers.set("Authorization", "Bearer " + window.JARVIS_API_TOKEN)' in shared
