using Elmfield.Appointments.Api.Application;
using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Api.Http;

public static class Endpoints
{
    public static void MapAppointmentsApi(this WebApplication app)
    {
        app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

        var api = app.MapGroup("/api");

        api.MapGet("/patients", (string? name, SchedulingService service) =>
            string.IsNullOrWhiteSpace(name)
                ? Results.Json(new { code = "NAME_REQUIRED", detail = "Query parameter 'name' is required." }, statusCode: 400)
                : Results.Ok(service.FindPatients(name)));

        api.MapGet("/patients/{patientId}/appointments", (string patientId, SchedulingService service) =>
            service.ListAppointments(patientId) is { } found
                ? Results.Ok(found.Select(AppointmentDto.From))
                : Results.Json(
                    new { code = ReasonCode.PatientNotFound.ToWire(), detail = "No patient with that ID exists." },
                    statusCode: 404));

        api.MapPost("/appointments", (BookingRequestDto? request, SchedulingService service, ILoggerFactory logs) =>
        {
            if (request is null || string.IsNullOrWhiteSpace(request.PatientId)
                || string.IsNullOrWhiteSpace(request.Department) || string.IsNullOrWhiteSpace(request.PreferredDay))
            {
                return Results.Json(
                    new { code = "INVALID_REQUEST", detail = "patientId, department and preferredDay are required." },
                    statusCode: 400);
            }

            var log = logs.CreateLogger("Appointments");
            var result = service.Book(request.PatientId, request.Department, request.PreferredDay);
            switch (result)
            {
                case BookingResult.Booked booked:
                    log.LogInformation("Booked {AppointmentId} for {PatientId}", booked.Appointment.AppointmentId, request.PatientId);
                    return Results.Created(
                        $"/api/patients/{booked.Appointment.PatientId}/appointments",
                        new { appointment = AppointmentDto.From(booked.Appointment) });

                case BookingResult.Duplicate duplicate:
                    log.LogInformation("Refused duplicate for {PatientId}", request.PatientId);
                    return Results.Json(
                        new
                        {
                            code = ReasonCode.DuplicateAppointment.ToWire(),
                            detail = duplicate.Detail,
                            existingAppointment = AppointmentDto.From(duplicate.Existing),
                        },
                        statusCode: 409);

                case BookingResult.Rejected rejected:
                    log.LogInformation("Rejected booking for {PatientId}: {Code}", request.PatientId, rejected.Code.ToWire());
                    return Results.Json(
                        new { code = rejected.Code.ToWire(), detail = rejected.Detail },
                        statusCode: rejected.Code == ReasonCode.PatientNotFound ? 404 : 422);

                default:
                    throw new InvalidOperationException("Unhandled booking result");
            }
        });
    }
}
