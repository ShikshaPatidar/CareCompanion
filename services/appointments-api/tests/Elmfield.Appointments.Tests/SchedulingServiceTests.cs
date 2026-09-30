using Elmfield.Appointments.Api.Application;
using Elmfield.Appointments.Api.Domain;
using Xunit;

namespace Elmfield.Appointments.Tests;

/// <summary>
/// Mirrors tests/test_scheduling_service.py in the Python project: the two implementations
/// must make the same decisions, and these cases pin that contract from the .NET side.
/// </summary>
public class SchedulingServiceTests
{
    private const string Whitfield = "PAT-1001";
    private const string Adeyemi = "PAT-1002";
    private const string Nair = "PAT-1004";

    private static readonly DateOnly Today = new(2026, 9, 28); // a Monday

    private static (SchedulingService Service, InMemoryAppointments Appointments) Create()
    {
        var hospital = new HospitalOptions
        {
            Departments =
            {
                new DepartmentOptions { Name = "Cardiology", Location = "Outpatients Block A, Clinic 3", Provider = "Dr. R. Bhatt" },
                new DepartmentOptions { Name = "General Medicine", Location = "Outpatients Block A, Clinic 1", Provider = "Dr. M. Haddad" },
                new DepartmentOptions
                {
                    Name = "Phlebotomy (Blood Tests)", Location = "Outpatients Block A, Level 1",
                    Provider = "Outpatient Phlebotomy", Aliases = { "blood test", "phlebotomy" },
                },
            },
        };
        var patients = new InMemoryPatients(
            new PatientSummary(Whitfield, "Susan Whitfield"),
            new PatientSummary(Adeyemi, "Tunde Adeyemi"),
            new PatientSummary(Nair, "Priya Nair"),
            new PatientSummary("PAT-1005", "Priya Nayar"));
        var appointments = new InMemoryAppointments(
            new Appointment("APT-2002", Whitfield, "Cardiology", "Dr. R. Bhatt",
                new DateTime(2026, 10, 9, 10, 0, 0), "Outpatients Block A, Clinic 3", AppointmentStatus.Confirmed),
            new Appointment("APT-2001", Adeyemi, "Orthopaedics", "Dr. S. Mistry",
                new DateTime(2026, 10, 6, 9, 30, 0), "Outpatients Block B, Clinic 4", AppointmentStatus.Confirmed));
        return (new SchedulingService(patients, appointments, hospital, new FixedClock(Today)), appointments);
    }

    [Fact]
    public void Books_first_free_slot_and_persists()
    {
        var (service, appointments) = Create();

        var result = Assert.IsType<BookingResult.Booked>(service.Book(Whitfield, "blood test", "2026-10-06"));

        Assert.Equal("Phlebotomy (Blood Tests)", result.Appointment.Department);
        Assert.Equal(new DateTime(2026, 10, 6, 9, 0, 0), result.Appointment.StartsAt);
        Assert.Contains(appointments.ForPatient(Whitfield), a => a.AppointmentId == result.Appointment.AppointmentId);
    }

    [Fact]
    public void Slot_skips_a_time_the_department_has_already_given_away()
    {
        var (service, _) = Create();
        service.Book(Whitfield, "blood test", "2026-10-06"); // takes 09:00 in the phlebotomy clinic

        var second = Assert.IsType<BookingResult.Booked>(service.Book(Nair, "blood test", "2026-10-06"));

        Assert.Equal(new DateTime(2026, 10, 6, 9, 30, 0), second.Appointment.StartsAt);
    }

    [Fact]
    public void Slot_skips_a_time_the_patient_is_already_busy()
    {
        var (service, _) = Create();
        service.Book(Whitfield, "blood test", "2026-10-06");

        var second = Assert.IsType<BookingResult.Booked>(service.Book(Whitfield, "General Medicine", "2026-10-06"));

        Assert.Equal(new DateTime(2026, 10, 6, 9, 30, 0), second.Appointment.StartsAt);
    }

    [Fact]
    public void Duplicate_within_window_is_refused_and_nothing_is_added()
    {
        var (service, appointments) = Create();

        var result = Assert.IsType<BookingResult.Duplicate>(service.Book(Whitfield, "Cardiology", "2026-10-15"));

        Assert.Equal("APT-2002", result.Existing.AppointmentId);
        Assert.Single(appointments.ForPatient(Whitfield));
    }

    [Fact]
    public void Same_department_outside_the_window_is_allowed()
    {
        var (service, _) = Create();

        Assert.IsType<BookingResult.Booked>(service.Book(Whitfield, "Cardiology", "2026-11-30"));
    }

    [Theory]
    [InlineData("PAT-9999", "Cardiology", "2026-10-20", ReasonCode.PatientNotFound)]
    [InlineData(Whitfield, "Dentistry", "2026-10-20", ReasonCode.UnknownDepartment)]
    [InlineData(Whitfield, "Phlebotomy", "20/10/2026", ReasonCode.BadDateFormat)]
    [InlineData(Whitfield, "Phlebotomy", "2026-02-30", ReasonCode.BadDateFormat)]
    [InlineData(Whitfield, "Phlebotomy", "2026-10-20; DROP TABLE", ReasonCode.BadDateFormat)]
    [InlineData(Whitfield, "Phlebotomy", "2026-09-28", ReasonCode.DateNotInFuture)]
    [InlineData(Whitfield, "Phlebotomy", "2020-01-01", ReasonCode.DateNotInFuture)]
    [InlineData(Whitfield, "Phlebotomy", "2026-10-10", ReasonCode.NotAWorkingDay)] // Saturday
    [InlineData(Whitfield, "Phlebotomy", "2027-06-01", ReasonCode.TooFarAhead)]
    public void Rejections_carry_a_reason_code(string patient, string department, string day, ReasonCode expected)
    {
        var (service, _) = Create();

        var result = Assert.IsType<BookingResult.Rejected>(service.Book(patient, department, day));

        Assert.Equal(expected, result.Code);
    }

    [Fact]
    public void Unknown_patient_has_no_appointment_list()
    {
        var (service, _) = Create();

        Assert.Null(service.ListAppointments("PAT-9999"));
    }

    [Fact]
    public void Ambiguous_name_returns_every_match()
    {
        var (service, _) = Create();

        Assert.Equal(2, service.FindPatients("Priya").Count);
        Assert.Empty(service.FindPatients("   "));
    }

    [Fact]
    public void Reason_codes_use_the_wire_names_the_python_client_expects()
    {
        Assert.Equal("DUPLICATE_APPOINTMENT", ReasonCode.DuplicateAppointment.ToWire());
        Assert.Equal("NOT_A_WORKING_DAY", ReasonCode.NotAWorkingDay.ToWire());
        Assert.Equal("PATIENT_NOT_FOUND", ReasonCode.PatientNotFound.ToWire());
    }
}
