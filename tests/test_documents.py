import json

import pytest

from carecompanion.documents.structured import extract_structured, parse_discharge_json
from carecompanion.documents.verify import verify_summary
from carecompanion.domain.errors import ExtractionError

GOOD = {
    "patient_name": "Susan Whitfield",
    "discharge_date": "2026-09-25",
    "diagnosis": "Coronary artery disease; status post PCI (drug-eluting stent, LAD)",
    "medications": [
        {"name": "Aspirin", "dose": "75 mg", "schedule": "once daily"},
        {"name": "Clopidogrel", "dose": "75 mg", "schedule": "once daily"},
    ],
    "follow_up": [{"department": "Cardiology", "timeframe": "2 weeks"}],
    "activity_limits": ["No lifting over 5 kg for 5 days"],
    "warning_signs": ["Chest pain or pressure", "Fainting"],
}


def test_parses_valid_json_including_code_fences():
    record = parse_discharge_json("```json\n" + json.dumps(GOOD) + "\n```")
    assert record.patient_name == "Susan Whitfield" and record.medications[1].name == "Clopidogrel"
    assert record.to_dict()["discharge_date"] == "2026-09-25"


def test_single_follow_up_object_is_tolerated():
    data = {**GOOD, "follow_up": {"department": "Cardiology", "timeframe": "2 weeks"}}
    assert parse_discharge_json(json.dumps(data)).follow_up[0].department == "Cardiology"


@pytest.mark.parametrize(
    "mutation",
    [
        {"discharge_date": "25/09/2026"},
        {"medications": []},
        {"diagnosis": ""},
        {"medications": [{"name": "Aspirin", "dose": "75 mg"}]},
        {"warning_signs": "chest pain"},
    ],
)
def test_invalid_records_are_rejected(mutation):
    with pytest.raises(ExtractionError):
        parse_discharge_json(json.dumps({**GOOD, **mutation}))


def test_non_json_is_rejected():
    with pytest.raises(ExtractionError):
        parse_discharge_json("Sure! Here is the JSON you asked for")


def test_extraction_retries_once_then_succeeds():
    replies = iter(["not json", json.dumps(GOOD)])

    class Resp:
        def __init__(self, text):
            self.output_text = text

    class Client:
        class responses:  # noqa: N801
            @staticmethod
            def create(model, input):
                return Resp(next(replies))

    assert extract_structured(Client(), "m", "prompt", "note").patient_name == "Susan Whitfield"


def test_extraction_gives_up_after_retry():
    class Client:
        class responses:  # noqa: N801
            @staticmethod
            def create(model, input):
                return type("R", (), {"output_text": "nope"})()

    with pytest.raises(ExtractionError):
        extract_structured(Client(), "m", "p", "n")


def test_verify_summary_catches_missing_facts_and_bad_numbers(guards):
    record = parse_discharge_json(json.dumps(GOOD))
    good = (
        "You had a stent. Take Aspirin 75 mg once daily and Clopidogrel 75 mg once daily. "
        "Call 999 in an emergency. Questions? Call the ward advice line on 020 7946 0142."
    )
    kwargs = {"required_contact": "020 7946 0142", "output_guard": guards[1]}
    assert verify_summary(good, record, **kwargs).passed
    bad = good.replace("Clopidogrel 75 mg", "Clopidogrel 150 mg").replace("999", "911")
    report = verify_summary(bad, record, **kwargs)
    assert not report.passed and any("dose" in p for p in report.problems)
    assert any("999" in p or "911" in p for p in report.problems)
