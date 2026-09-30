using Elmfield.Appointments.Api.Application;
using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Tests;

internal sealed class FixedClock(DateOnly today) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => new(today.ToDateTime(new TimeOnly(12, 0)), TimeSpan.Zero);
}

internal sealed class InMemoryPatients(params PatientSummary[] patients) : IPatientRepository
{
    public IReadOnlyList<PatientSummary> SearchByName(string name)
    {
        var needle = name.Trim().ToLowerInvariant();
        return needle.Length == 0
            ? new List<PatientSummary>()
            : patients.Where(p => p.Name.ToLowerInvariant().Contains(needle)).ToList();
    }

    public bool Exists(string patientId) => patients.Any(p => p.Id == patientId);
}

internal sealed class InMemoryAppointments(params Appointment[] seed) : IAppointmentRepository
{
    private readonly List<Appointment> _items = [.. seed];

    public IReadOnlyList<Appointment> ForPatient(string patientId) =>
        _items.Where(a => a.PatientId == patientId).ToList();

    public IReadOnlyList<Appointment> ForDepartmentOn(string department, DateOnly day) =>
        _items.Where(a => a.Department == department && DateOnly.FromDateTime(a.StartsAt) == day).ToList();

    public string NextId() =>
        $"APT-{_items.Select(a => int.Parse(a.AppointmentId[4..])).DefaultIfEmpty(2000).Max() + 1}";

    public void Add(Appointment appointment) => _items.Add(appointment);
}
