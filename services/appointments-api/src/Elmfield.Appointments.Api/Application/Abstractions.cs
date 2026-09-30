using Elmfield.Appointments.Api.Domain;

namespace Elmfield.Appointments.Api.Application;

public interface IPatientRepository
{
    IReadOnlyList<PatientSummary> SearchByName(string name);
    bool Exists(string patientId);
}

public interface IAppointmentRepository
{
    IReadOnlyList<Appointment> ForPatient(string patientId);
    IReadOnlyList<Appointment> ForDepartmentOn(string department, DateOnly day);
    string NextId();
    void Add(Appointment appointment);
}
