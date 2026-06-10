from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product_moderation", "0003_rename_moderated_status_to_approved"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmoderationfieldreport",
            name="field_path",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="productmoderationfieldreport",
            name="message",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="productmoderationfieldreport",
            name="severity",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
