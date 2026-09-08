from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("patients", "0041_calllog_reason")]
    operations = [
        migrations.CreateModel(name="PatientIdentityAllocator", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("high_water", models.PositiveBigIntegerField(default=0)),
        ], options={"constraints": [models.CheckConstraint(condition=models.Q(pk=1), name="patient_identity_singleton")]}),
        migrations.CreateModel(name="PatientIdentityIssuance", fields=[
            ("mtno", models.CharField(max_length=32, primary_key=True, serialize=False)),
            ("identity_uuid", models.UUIDField(unique=True)),
        ]),
        migrations.AddField(model_name="patient", name="mtno", field=models.CharField(max_length=32, null=True, unique=True, editable=False, blank=True)),
        migrations.AddField(model_name="patient", name="identity_uuid", field=models.UUIDField(null=True, unique=True, editable=False)),
        migrations.AlterField(model_name="patient", name="uhid", field=models.CharField(max_length=64, blank=True, default="")),
        migrations.AddConstraint(model_name="patient", constraint=models.UniqueConstraint(fields=["uhid"], condition=~models.Q(uhid=""), name="patient_nonblank_uhid_unique")),
    ]
