namespace Elmfield.Appointments.Api.Domain;

/// <summary>Bound from hospital.json, which is generated from config/hospital.toml.</summary>
public sealed class HospitalOptions
{
    public SchedulingOptions Scheduling { get; set; } = new();
    public List<DepartmentOptions> Departments { get; set; } = new();
}

public sealed class SchedulingOptions
{
    public int[] WorkingDays { get; set; } = [1, 2, 3, 4, 5]; // ISO: Monday = 1
    public string OpenTime { get; set; } = "09:00";
    public string CloseTime { get; set; } = "16:30";
    public int SlotMinutes { get; set; } = 30;
    public int MaxDaysAhead { get; set; } = 180;
    public int DuplicateWindowDays { get; set; } = 14;
}

public sealed class DepartmentOptions
{
    public string Name { get; set; } = "";
    public string Location { get; set; } = "";
    public string Provider { get; set; } = "";
    public List<string> Aliases { get; set; } = new();
}
