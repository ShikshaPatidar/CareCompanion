using System.Globalization;
using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Api.Http;

/// <summary>Wire shape of an appointment; identical to the seed data and the Python client.</summary>
public sealed record AppointmentDto(
    string ResourceType, string AppointmentId, string PatientId, string Department,
    string Provider, string Datetime, string Location, string Status)
{
    public static AppointmentDto From(Appointment a) => new(
        "Appointment", a.AppointmentId, a.PatientId, a.Department, a.Provider,
        a.StartsAt.ToString("yyyy-MM-ddTHH:mm", CultureInfo.InvariantCulture),
        a.Location, a.Status.ToString().ToLowerInvariant());
}

public sealed record BookingRequestDto(string? PatientId, string? Department, string? PreferredDay);
