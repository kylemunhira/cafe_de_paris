import random

from django.db import migrations, models
import django.core.validators


def assign_access_codes(apps, schema_editor):
    StaffProfile = apps.get_model("accounts", "StaffProfile")
    used = set(
        StaffProfile.objects.exclude(access_code__isnull=True)
        .exclude(access_code="")
        .values_list("access_code", flat=True)
    )
    for profile in StaffProfile.objects.filter(access_code__isnull=True):
        for _ in range(10000):
            code = f"{random.randint(0, 9999):04d}"
            if code not in used:
                used.add(code)
                profile.access_code = code
                profile.save(update_fields=["access_code"])
                break
        else:
            raise RuntimeError("Could not allocate unique 4-digit access codes.")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_staffprofile_kitchen_station"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="access_code",
            field=models.CharField(
                blank=True,
                help_text="4-digit code for login and manager POS overrides.",
                max_length=4,
                null=True,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Access code must be exactly 4 digits.",
                        regex="^\\d{4}$",
                    )
                ],
            ),
        ),
        migrations.RunPython(assign_access_codes, migrations.RunPython.noop),
    ]
