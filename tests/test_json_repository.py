import json

from carecompanion.scheduling.json_repository import JsonAppointmentRepository


def test_seed_is_copied_and_never_modified(settings, tmp_path):
    seed = settings.data_dir / "appointments.json"
    before = seed.read_text()
    repo = JsonAppointmentRepository(seed, tmp_path / "state.json")
    assert repo.next_id() == "APT-2008"
    assert seed.read_text() == before
    assert json.loads((tmp_path / "state.json").read_text())[0]["appointmentId"] == "APT-2001"


def test_changes_survive_a_restart(settings, gateway, tmp_path):
    from carecompanion.domain import BookingRequest

    gateway.book(BookingRequest("PAT-1001", "blood test", "2026-10-06"))
    reopened = JsonAppointmentRepository(
        settings.data_dir / "appointments.json", tmp_path / "appointments.json"
    )
    assert any(a.appointment_id == "APT-2008" for a in reopened.for_patient("PAT-1001"))
