from django.db import migrations, models


def grant_pos_access_to_retail_branch_staff(apps, schema_editor):
    StaffProfile = apps.get_model("accounts", "StaffProfile")
    StaffProfile.objects.filter(branch__branch_type="branch").update(pos_access=True)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_staffprofile_role"),
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="pos_access",
            field=models.BooleanField(
                default=False,
                help_text="Allows web and desktop POS for this user.",
            ),
        ),
        migrations.RunPython(
            grant_pos_access_to_retail_branch_staff,
            migrations.RunPython.noop,
        ),
    ]
