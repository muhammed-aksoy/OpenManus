"""Diagnostics for an unreachable model server.

A user pointing OpenManus at a local Ollama or LM Studio hits container
networking, not a product bug — but the raw error ("Connection refused") never
says so. These tests pin the explanations, because a wrong hint is worse than
none: it sends someone to fix the wrong thing.
"""

import pytest

from server.tasks import resolve_llm_connection, unreachable_hint


class FakeTask:
    def __init__(self):
        self.events = []

    def emit(self, event_type, data):
        self.events.append((event_type, data))

    def types(self):
        return [event_type for event_type, _ in self.events]

    def payload(self, event_type):
        return next(data for kind, data in self.events if kind == event_type)


# ---------------------------------------------------------------------------
# Hints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "0.0.0.0"])
def test_loopback_inside_a_container_names_the_real_problem(host, monkeypatch):
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)

    hint = unreachable_hint(f"http://{host}:11434", "Connection refused")

    assert "container" in hint
    assert "host.docker.internal" in hint


def test_loopback_outside_a_container_is_not_blamed_on_docker(monkeypatch):
    """Running bare metal, 127.0.0.1 is legitimate — do not misdirect."""
    monkeypatch.setattr("server.tasks._running_in_container", lambda: False)

    hint = unreachable_hint("http://127.0.0.1:11434", "Connection refused")

    assert "host.docker.internal" not in hint


def test_a_timeout_points_at_the_firewall_not_the_address(monkeypatch):
    """Refused means nothing listening; timed out means something dropped it."""
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)

    hint = unreachable_hint("http://172.17.0.1:11434", "<urlopen error timed out>")

    assert "firewall" in hint
    assert "ufw" in hint


def test_the_firewall_hint_names_this_container_s_own_subnet(monkeypatch):
    """docker compose uses a project network, not the 172.17 default bridge.

    Naming the wrong range makes the user allow a subnet that is not theirs,
    see no change, and rule the firewall out incorrectly.
    """
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)
    monkeypatch.setattr("server.tasks._container_subnet", lambda: "172.18.0.0/16")

    hint = unreachable_hint("http://host.docker.internal:11434", "timed out")

    assert "172.18.0.0/16" in hint
    assert "172.17.0.0/16" not in hint


def test_the_firewall_hint_degrades_when_the_subnet_is_unknown(monkeypatch):
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)
    monkeypatch.setattr("server.tasks._container_subnet", lambda: "")

    hint = unreachable_hint("http://host.docker.internal:11434", "timed out")

    assert "<your container subnet>" in hint


def test_an_unresolvable_name_points_at_extra_hosts(monkeypatch):
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)

    hint = unreachable_hint(
        "http://host.docker.internal:11434",
        "<urlopen error [Errno -2] Name or service not known>",
    )

    assert "extra_hosts" in hint
    assert "host-gateway" in hint


def test_an_ordinary_remote_failure_gets_no_invented_hint(monkeypatch):
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)

    assert unreachable_hint("https://api.openai.com/v1", "HTTP 401") == ""


def test_a_malformed_base_url_does_not_raise(monkeypatch):
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)

    assert unreachable_hint("::::not a url::::", "boom") == ""
    assert unreachable_hint("", "boom") == ""


# ---------------------------------------------------------------------------
# Surfacing
# ---------------------------------------------------------------------------


def test_an_unreachable_server_is_reported_before_the_run(monkeypatch):
    monkeypatch.setattr(
        "server.tasks._is_connection_healthy",
        lambda connection, timeout=5: (False, "Connection refused"),
    )
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)
    task = FakeTask()

    resolve_llm_connection(
        {"base_url": "http://127.0.0.1:11434", "api_type": "ollama"}, task
    )

    assert "llm_unreachable" in task.types()
    payload = task.payload("llm_unreachable")
    assert payload["base_url"] == "http://127.0.0.1:11434"
    assert payload["detail"] == "Connection refused"
    assert "host.docker.internal" in payload["hint"]


def test_the_run_still_proceeds_on_a_failed_preflight(monkeypatch):
    """The probe only checks a models endpoint; some gateways refuse it."""
    monkeypatch.setattr(
        "server.tasks._is_connection_healthy",
        lambda connection, timeout=5: (False, "HTTP 404"),
    )
    task = FakeTask()
    connection = {"base_url": "https://gateway.example/v1", "api_type": "openai"}

    selected = resolve_llm_connection(connection, task)

    assert selected["base_url"] == "https://gateway.example/v1"


def test_a_healthy_connection_reports_nothing_alarming(monkeypatch):
    monkeypatch.setattr(
        "server.tasks._is_connection_healthy",
        lambda connection, timeout=5: (True, "v1/models ok"),
    )
    task = FakeTask()

    selected = resolve_llm_connection(
        {"base_url": "http://host.docker.internal:11434", "api_type": "ollama"}, task
    )

    assert "llm_unreachable" not in task.types()
    assert selected["base_url"] == "http://host.docker.internal:11434"


def test_the_first_failure_is_the_one_explained(monkeypatch):
    """The primary connection is what the user configured; blame that one."""
    monkeypatch.setattr(
        "server.tasks._is_connection_healthy",
        lambda connection, timeout=5: (False, f"failed {connection.get('base_url')}"),
    )
    monkeypatch.setattr("server.tasks._running_in_container", lambda: True)
    task = FakeTask()

    resolve_llm_connection(
        {
            "base_url": "http://127.0.0.1:11434",
            "api_type": "ollama",
            "fallback_chain": [{"base_url": "https://backup.example/v1"}],
        },
        task,
    )

    payload = task.payload("llm_unreachable")
    assert payload["detail"] == "failed http://127.0.0.1:11434"
    assert payload["attempted"] == 2
