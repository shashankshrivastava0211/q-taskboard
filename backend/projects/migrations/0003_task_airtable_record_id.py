from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='airtable_record_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
