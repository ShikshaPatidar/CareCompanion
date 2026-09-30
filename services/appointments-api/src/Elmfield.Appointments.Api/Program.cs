using System.Security.Cryptography;
using System.Text;
using Elmfield.Appointments.Api.Http;
using Elmfield.Appointments.Api.Application;
using Elmfield.Appointments.Api.Domain;
using Elmfield.Appointments.Api.Infrastructure;

var builder = WebApplication.CreateBuilder(args);

// hospital.json is generated from config/hospital.toml (`carecompanion export-api-config`).
builder.Configuration.AddJsonFile("hospital.json", optional: false, reloadOnChange: false);

var hospital = builder.Configuration.GetSection("Hospital").Get<HospitalOptions>()
               ?? throw new InvalidOperationException("Missing 'Hospital' configuration (hospital.json).");
var data = builder.Configuration.GetSection("Data").Get<DataOptions>() ?? new DataOptions();
var apiKey = builder.Configuration["Api:Key"] ?? "";
var fixedDate = builder.Configuration["Clock:FixedDate"];

string Resolve(string path) => Path.GetFullPath(Path.Combine(builder.Environment.ContentRootPath, path));

builder.Services.AddSingleton(hospital);
builder.Services.AddSingleton<TimeProvider>(_ =>
    string.IsNullOrWhiteSpace(fixedDate) ? TimeProvider.System : new FixedDateTimeProvider(DateOnly.ParseExact(fixedDate, "yyyy-MM-dd")));
builder.Services.AddSingleton<IPatientRepository>(_ => new JsonPatientRepository(Resolve(data.PatientsPath)));
builder.Services.AddSingleton<IAppointmentRepository>(_ =>
    new JsonAppointmentRepository(Resolve(data.AppointmentsSeedPath), Resolve(data.StatePath)));
builder.Services.AddSingleton<SchedulingService>();

var app = builder.Build();

if (string.IsNullOrEmpty(apiKey))
    app.Logger.LogWarning("Api:Key is empty: authentication is DISABLED. Set Api__Key for anything but local development.");

// Simple shared-secret authentication for /api/*. /health stays open for probes.
app.Use(async (context, next) =>
{
    if (!string.IsNullOrEmpty(apiKey) && context.Request.Path.StartsWithSegments("/api"))
    {
        var supplied = context.Request.Headers["X-Api-Key"].ToString();
        var ok = CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(supplied), Encoding.UTF8.GetBytes(apiKey));
        if (!ok)
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            await context.Response.WriteAsJsonAsync(new { code = "UNAUTHORIZED", detail = "Missing or invalid API key." });
            return;
        }
    }
    await next();
});

app.MapAppointmentsApi();
app.Run();

internal sealed class DataOptions
{
    public string PatientsPath { get; set; } = "../../../../data/patients.json";
    public string AppointmentsSeedPath { get; set; } = "../../../../data/appointments.json";
    public string StatePath { get; set; } = "../../../../var/dotnet-appointments.json";
}

/// <summary>Pins "today" so demos and evaluations are repeatable (Clock:FixedDate).</summary>
internal sealed class FixedDateTimeProvider(DateOnly date) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => new(date.ToDateTime(new TimeOnly(12, 0)), TimeSpan.Zero);
}
