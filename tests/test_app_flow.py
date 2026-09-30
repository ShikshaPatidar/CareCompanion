"""The application flow, with a fake coordinator so no cloud is needed."""

import pytest

from carecompanion.app import CareCompanionApp


class FakeCoordinator:
    def __init__(self, reply="Happy to help.", fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def create_session(self):
        return object()

    async def run(self, text, session=None):
        if self.fail:
            raise RuntimeError("model down")
        self.calls.append(text)
        return self.reply


def make_app(guards, audit, coordinator, guardrails=True):
    return CareCompanionApp(coordinator, guards[0], guards[1], audit, guardrails_enabled=guardrails)


async def test_emergency_never_reaches_the_model(guards, audit):
    coordinator = FakeCoordinator()
    app = make_app(guards, audit, coordinator)
    reply = await app.ask(app.new_session(), "I have chest pain")
    assert reply.blocked and reply.category == "emergency" and "999" in reply.text
    assert coordinator.calls == []
    assert audit.since(0)[0]["event"] == "guard_input"


async def test_normal_message_passes_through_and_is_audited_without_content(guards, audit):
    coordinator = FakeCoordinator("The ICU opens at 11:00 am.")
    app = make_app(guards, audit, coordinator)
    reply = await app.ask(app.new_session(), "ICU hours?")
    assert reply.text == "The ICU opens at 11:00 am." and not reply.blocked
    logged = str(audit.since(0))
    assert "ICU hours?" not in logged and "<10 chars>" in logged


async def test_output_guard_replaces_a_bad_reply(guards, audit):
    app = make_app(guards, audit, FakeCoordinator("Call 911 now or 020 7946 0999."))
    reply = await app.ask(app.new_session(), "Who do I call about parking?")
    assert reply.blocked and reply.category == "output"
    assert "911" not in reply.text and "020 7946 0119" in reply.text


async def test_model_failure_degrades_gracefully(guards, audit):
    app = make_app(guards, audit, FakeCoordinator(fail=True))
    reply = await app.ask(app.new_session(), "Hello")
    assert "something went wrong" in reply.text.lower()
    assert any(e["event"] == "model_error" for e in audit.since(0))


async def test_guardrails_can_be_disabled_for_baseline_evaluation(guards, audit):
    coordinator = FakeCoordinator("ok")
    app = make_app(guards, audit, coordinator, guardrails=False)
    reply = await app.ask(app.new_session(), "I have chest pain")
    assert not reply.blocked and coordinator.calls == ["I have chest pain"]


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_input_is_handled(guards, audit, text):
    coordinator = FakeCoordinator()
    app = make_app(guards, audit, coordinator)
    await app.ask(app.new_session(), text)
    assert coordinator.calls == []


async def test_overlong_input_is_rejected(guards, audit):
    coordinator = FakeCoordinator()
    app = make_app(guards, audit, coordinator)
    reply = await app.ask(app.new_session(), "x" * 2001)
    assert "too long" in reply.text and coordinator.calls == []
