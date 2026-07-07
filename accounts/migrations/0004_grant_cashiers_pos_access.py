from django.db import migrations


def grant_cashiers_pos_access(apps, schema_editor):
    StaffProfile = apps.get_model("accounts", "StaffProfile")
    StaffProfile.objects.filter(role="cashier", pos_access=False).update(pos_access=True)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_staffprofile_pos_access"),
    ]

    operations = [
        migrations.RunPython(grant_cashiers_pos_access, migrations.RunPython.noop),
    ]
