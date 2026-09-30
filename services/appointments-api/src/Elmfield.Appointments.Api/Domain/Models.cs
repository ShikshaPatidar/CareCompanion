namespace Elmfield.Appointments.Api.Domain;

public enum AppointmentStatus { Confirmed, Pending, Cancelled }

/// <summary>Machine-readable reasons. The wire names match the Python client's ReasonCode.</summary>
public enum ReasonCode
{
    PatientNotFound,
    UnknownDepartment,
    BadDateFormat,
    DateNotInFuture,
    NotAWorkingDay,
    TooFarAhead,
    DuplicateAppointment,
    NoSlotAvailable,
}

public static class ReasonCodeExtensions
{
    public static string ToWire(this ReasonCode code) => code switch
    {
        ReasonCode.PatientNotFound => "PATIENT_NOT_FOUND",
        ReasonCode.UnknownDepartment => "UNKNOWN_DEPARTMENT",
        ReasonCode.BadDateFormat => "BAD_DATE_FORMAT",
        ReasonCode.DateNotInFuture => "DATE_NOT_IN_FUTURE",
        ReasonCode.NotAWorkingDay => "NOT_A_WORKING_DAY",
        ReasonCode.TooFarAhead => "TOO_FAR_AHEAD",
        ReasonCode.DuplicateAppointment => "DUPLICATE_APPOINTMENT",
        ReasonCode.NoSlotAvailable => "NO_SLOT_AVAILABLE",
        _ => throw new ArgumentOutOfRangeException(nameof(code), code, null),
    };
}

/// <summary>The minimum needed to identify a patient (data minimisation).</summary>
public sealed record PatientSummary(string Id, string Name);

public sealed record Appointment(
    string AppointmentId,
    string PatientId,
    string Department,
    string Provider,
    DateTime StartsAt,
    string Location,
    AppointmentStatus Status)
{
    public bool IsActive => Status != AppointmentStatus.Cancelled;
}

/// <summary>Outcome of a booking attempt. Expected outcomes are values, not exceptions.</summary>
public abstract record BookingResult
{
    private BookingResult() { }

    public sealed record Booked(Appointment Appointment) : BookingResult;
    public sealed record Duplicate(Appointment Existing, string Detail) : BookingResult;
    public sealed record Rejected(ReasonCode Code, string Detail) : BookingResult;
}
