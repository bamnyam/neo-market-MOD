from django.db import migrations, models


def forwards(apps, schema_editor):
    product_moderation = apps.get_model("product_moderation", "ProductModeration")
    product_moderation.objects.filter(status="MODERATED").update(status="APPROVED")


def backwards(apps, schema_editor):
    product_moderation = apps.get_model("product_moderation", "ProductModeration")
    product_moderation.objects.filter(status="APPROVED").update(status="MODERATED")


class Migration(migrations.Migration):
    dependencies = [
        ("product_moderation", "0002_alter_productmoderation_queue_priority_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="productmoderation",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("IN_REVIEW", "In review"),
                    ("APPROVED", "Approved"),
                    ("BLOCKED", "Blocked"),
                    ("HARD_BLOCKED", "Hard blocked"),
                ],
                default="PENDING",
                max_length=32,
            ),
        ),
    ]
