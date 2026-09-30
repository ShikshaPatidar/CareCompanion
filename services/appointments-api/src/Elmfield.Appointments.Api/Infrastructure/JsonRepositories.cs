using System.Globalization;
using System.Text.Json;
using Elmfield.Appointments.Api.Application;
using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Api.Infrastructure;

internal static class JsonFiles
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    public const string DateFormat = "yyyy-MM-ddTHH:mm";
}

/// <summary>Reads only id and name. Dates of birth, phone numbers and notes are never loaded.</summary>
public sealed class JsonPatientRepository : IPatientRepository
{
    private sealed record PatientRecord(string Id, string Name);

    private readonly List<PatientSummary> _patients;

    public JsonPatientRepository(string path)
    {
        var records = JsonSerializer.Deserialize<List<PatientRecord>>(File.ReadAllText(path), JsonFiles.Options)
                      ?? throw new InvalidDataException($"{path} is empty");
        _patients = records.Select(r => new PatientSummary(r.Id, r.Name)).ToList();
    }

    public IReadOnlyList<PatientSummary> SearchByName(string name)
    {
        var needle = string.Join(' ', name.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries));
        return needle.Length == 0
            ? new List<PatientSummary>()
            : _patients.Where(p => p.Name.ToLowerInvariant().Contains(needle, StringComparison.Ordinal)).ToList();
    }

    public bool Exists(string patientId) => _patients.Any(p => p.Id == patientId);
}

/// <summary>Seed data is read-only; every change is written to a separate state file.</summary>
public sealed class JsonAppointmentRepository : IAppointmentRepository
{
    private sealed record AppointmentRecord(
        string AppointmentId, string PatientId, string Department, string Provider,
        string Datetime, string Location, string Status);

    private readonly object _lock = new();
    private readonly string _statePath;
    private readonly List<Appointment> _items;

    public JsonAppointmentRepository(string seedPath, string statePath)
    {
        _statePath = statePath;
        if (!File.Exists(statePath))
        {
            Directory.CreateDirectory(Path.GetDirectoryName(statePath)!);
            File.Copy(seedPath, statePath);
        }
        var records = JsonSerializer.Deserialize<List<AppointmentRecord>>(File.ReadAllText(statePath), JsonFiles.Options)
                      ?? throw new InvalidDataException($"{statePath} is empty");
        _items = records.Select(ToDomain).ToList();
    }

    public IReadOnlyList<Appointment> ForPatient(string patientId)
    {
        lock (_lock) return _items.Where(a => a.PatientId == patientId).ToList();
    }

    public IReadOnlyList<Appointment> ForDepartmentOn(string department, DateOnly day)
    {
        lock (_lock)
            return _items.Where(a => a.Department == department && DateOnly.FromDateTime(a.StartsAt) == day).ToList();
    }

    public string NextId()
    {
        lock (_lock)
        {
            var highest = _items
                .Select(a => a.AppointmentId)
                .Where(id => id.StartsWith("APT-", StringComparison.Ordinal) && int.TryParse(id.AsSpan(4), out _))
                .Select(id => int.Parse(id.AsSpan(4), CultureInfo.InvariantCulture))
                .DefaultIfEmpty(2000)
                .Max();
            return $"APT-{highest + 1}";
        }
    }

    public void Add(Appointment appointment)
    {
        lock (_lock)
        {
            _items.Add(appointment);
            Persist();
        }
    }

    private void Persist()
    {
        // Write to a temp file then move it over the target, so a crash never leaves half a file.
        var temp = _statePath + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(_items.Select(ToRecord), JsonFiles.Options));
        File.Move(temp, _statePath, overwrite: true);
    }

    private static Appointment ToDomain(AppointmentRecord r) => new(
        r.AppointmentId, r.PatientId, r.Department, r.Provider,
        DateTime.ParseExact(r.Datetime, JsonFiles.DateFormat, CultureInfo.InvariantCulture),
        r.Location, Enum.Parse<AppointmentStatus>(r.Status, ignoreCase: true));

    private static AppointmentRecord ToRecord(Appointment a) => new(
        a.AppointmentId, a.PatientId, a.Department, a.Provider,
        a.StartsAt.ToString(JsonFiles.DateFormat, CultureInfo.InvariantCulture),
        a.Location, a.Status.ToString().ToLowerInvariant());
}
