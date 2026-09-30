using System.Globalization;
using System.Text.RegularExpressions;
using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Api.Application;

/// <summary>
/// The single place where "can this be booked?" is decided. Mirrors the Python
/// SchedulingService rule for rule; the shared behaviour is pinned by tests on both sides.
/// </summary>
public sealed partial class SchedulingService(
    IPatientRepository patients,
    IAppointmentRepository appointments,
    HospitalOptions hospital,
    TimeProvider clock)
{
    private readonly object _bookingLock = new(); // single instance; a database would use a transaction

    [GeneratedRegex(@"^\d{4}-\d{2}-\d{2}$")]
    private static partial Regex IsoDay();

    public IReadOnlyList<PatientSummary> FindPatients(string name) => patients.SearchByName(name);

    /// <summary>Appointments for a patient, or null if the patient does not exist.</summary>
    public IReadOnlyList<Appointment>? ListAppointments(string patientId) =>
        patients.Exists(patientId)
            ? appointments.ForPatient(patientId).OrderBy(a => a.StartsAt).ToList()
            : null;

    public BookingResult Book(string patientId, string departmentText, string preferredDay)
    {
        lock (_bookingLock)
        {
            if (!patients.Exists(patientId))
                return new BookingResult.Rejected(ReasonCode.PatientNotFound, "No patient with that ID exists.");

            var department = FindDepartment(departmentText);
            if (department is null)
            {
                var known = string.Join(", ", hospital.Departments.Select(d => d.Name));
                return new BookingResult.Rejected(ReasonCode.UnknownDepartment, $"Unknown department. Available: {known}.");
            }

            var check = ValidateDay(preferredDay);
            if (check.Rejection is not null) return check.Rejection;
            var day = check.Day;

            var duplicate = FindDuplicate(patientId, department, day);
            if (duplicate is not null)
            {
                return new BookingResult.Duplicate(
                    duplicate,
                    $"The patient already has a {department.Name} appointment within " +
                    $"{hospital.Scheduling.DuplicateWindowDays} days of the requested date.");
            }

            var start = FirstFreeSlot(patientId, department, day);
            if (start is null)
                return new BookingResult.Rejected(ReasonCode.NoSlotAvailable, $"No free slots in {department.Name} on that day.");

            var appointment = new Appointment(
                appointments.NextId(), patientId, department.Name, department.Provider,
                start.Value, department.Location, AppointmentStatus.Confirmed);
            appointments.Add(appointment);
            return new BookingResult.Booked(appointment);
        }
    }

    private DepartmentOptions? FindDepartment(string text)
    {
        var wanted = Normalise(text);
        return hospital.Departments.FirstOrDefault(d =>
            Normalise(d.Name) == wanted || d.Aliases.Any(a => Normalise(a) == wanted));
    }

    private static string Normalise(string text) =>
        string.Join(' ', text.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries));

    private readonly record struct DayCheck(DateOnly Day, BookingResult.Rejected? Rejection);

    private static DayCheck Reject(ReasonCode code, string detail) =>
        new(default, new BookingResult.Rejected(code, detail));

    private DayCheck ValidateDay(string raw)
    {
        var text = raw.Trim();
        if (!IsoDay().IsMatch(text)
            || !DateOnly.TryParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var day))
        {
            return Reject(ReasonCode.BadDateFormat, "Dates must be in the format YYYY-MM-DD.");
        }

        var policy = hospital.Scheduling;
        var today = DateOnly.FromDateTime(clock.GetUtcNow().UtcDateTime);
        if (day <= today)
            return Reject(ReasonCode.DateNotInFuture, "Appointments must be booked for a future date.");
        if (!policy.WorkingDays.Contains(IsoWeekday(day)))
            return Reject(ReasonCode.NotAWorkingDay, "Clinics run on weekdays only.");
        if (day > today.AddDays(policy.MaxDaysAhead))
            return Reject(ReasonCode.TooFarAhead, $"Appointments can be booked up to {policy.MaxDaysAhead} days ahead.");
        return new DayCheck(day, null);
    }

    private static int IsoWeekday(DateOnly day) => ((int)day.DayOfWeek + 6) % 7 + 1; // Monday = 1 ... Sunday = 7

    private Appointment? FindDuplicate(string patientId, DepartmentOptions department, DateOnly day)
    {
        var window = hospital.Scheduling.DuplicateWindowDays;
        return appointments.ForPatient(patientId)
            .Where(a => a.IsActive && a.Department == department.Name
                        && Math.Abs(DateOnly.FromDateTime(a.StartsAt).DayNumber - day.DayNumber) <= window)
            .OrderBy(a => Math.Abs(DateOnly.FromDateTime(a.StartsAt).DayNumber - day.DayNumber))
            .FirstOrDefault();
    }

    private DateTime? FirstFreeSlot(string patientId, DepartmentOptions department, DateOnly day)
    {
        var policy = hospital.Scheduling;
        var takenByDepartment = appointments.ForDepartmentOn(department.Name, day)
            .Where(a => a.IsActive).Select(a => a.StartsAt).ToHashSet();
        var takenByPatient = appointments.ForPatient(patientId)
            .Where(a => a.IsActive).Select(a => a.StartsAt).ToHashSet();

        var slot = day.ToDateTime(TimeOnly.ParseExact(policy.OpenTime, "HH:mm", CultureInfo.InvariantCulture));
        var close = day.ToDateTime(TimeOnly.ParseExact(policy.CloseTime, "HH:mm", CultureInfo.InvariantCulture));
        var step = TimeSpan.FromMinutes(policy.SlotMinutes);
        for (; slot + step <= close; slot += step)
        {
            if (!takenByDepartment.Contains(slot) && !takenByPatient.Contains(slot)) return slot;
        }
        return null;
    }
}
