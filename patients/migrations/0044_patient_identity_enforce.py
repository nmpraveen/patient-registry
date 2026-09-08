import uuid
from django.db import migrations, models


def install_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION patients_identity_immutable() RETURNS trigger AS $$
        DECLARE number bigint;
        BEGIN
            IF TG_TABLE_NAME = 'patients_patientidentityissuance' THEN
                IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Patient identity issuance is immutable'; END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF NEW.mtno IS DISTINCT FROM OLD.mtno OR NEW.identity_uuid IS DISTINCT FROM OLD.identity_uuid THEN
                    RAISE EXCEPTION 'Patient MTNO and identity binding are immutable';
                END IF;
            END IF;
            IF NEW.mtno !~ '^MT-[0-9]{6,19}$' THEN RAISE EXCEPTION 'Invalid MTNO'; END IF;
            number := substring(NEW.mtno from 4)::bigint;
            IF number < 1 OR NEW.mtno <> ('MT-' || CASE WHEN number < 1000000 THEN lpad(number::text, 6, '0') ELSE number::text END) THEN
                RAISE EXCEPTION 'Invalid canonical MTNO';
            END IF;
            IF TG_TABLE_NAME = 'patients_patient' AND NOT EXISTS (
                SELECT 1 FROM patients_patientidentityissuance WHERE mtno = NEW.mtno AND identity_uuid = NEW.identity_uuid
            ) THEN RAISE EXCEPTION 'Missing patient identity issuance'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER patient_identity_guard BEFORE INSERT OR UPDATE ON patients_patient
            FOR EACH ROW EXECUTE FUNCTION patients_identity_immutable();
        CREATE TRIGGER patient_issuance_guard BEFORE INSERT OR UPDATE OR DELETE ON patients_patientidentityissuance
            FOR EACH ROW EXECUTE FUNCTION patients_identity_immutable();
        CREATE FUNCTION patients_allocator_monotonic() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Patient identity allocator cannot be deleted'; END IF;
            IF NEW.high_water < OLD.high_water THEN RAISE EXCEPTION 'Patient identity allocator cannot decrease'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER patient_allocator_guard BEFORE UPDATE OR DELETE ON patients_patientidentityallocator
            FOR EACH ROW EXECUTE FUNCTION patients_allocator_monotonic();
    """)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS patient_identity_guard ON patients_patient;
        DROP TRIGGER IF EXISTS patient_issuance_guard ON patients_patientidentityissuance;
        DROP TRIGGER IF EXISTS patient_allocator_guard ON patients_patientidentityallocator;
        DROP FUNCTION IF EXISTS patients_identity_immutable();
        DROP FUNCTION IF EXISTS patients_allocator_monotonic();
    """)


class Migration(migrations.Migration):
    dependencies = [("patients", "0043_patient_identity_backfill")]
    operations = [
        migrations.AlterField(model_name="patient", name="mtno", field=models.CharField(max_length=32, unique=True, editable=False, blank=True)),
        migrations.AlterField(model_name="patient", name="identity_uuid", field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
        migrations.AddConstraint(model_name="patient", constraint=models.CheckConstraint(condition=~models.Q(mtno=""), name="patient_mtno_present")),
        migrations.RunPython(install_guards, remove_guards),
    ]
