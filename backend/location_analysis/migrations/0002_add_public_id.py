# Generated migration for public_id field

from django.db import migrations, models
import secrets


def generate_public_ids(apps, schema_editor):
    """Generate public_id for existing records."""
    LocationAnalysis = apps.get_model('location_analysis', 'LocationAnalysis')
    for analysis in LocationAnalysis.objects.filter(public_id=''):
        # Generate unique public_id
        for _ in range(10):
            new_id = secrets.token_urlsafe(16)[:24]
            if not LocationAnalysis.objects.filter(public_id=new_id).exists():
                analysis.public_id = new_id
                analysis.save(update_fields=['public_id'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('location_analysis', '0001_initial'),
    ]

    operations = [
        # Step 1: Add field as nullable
        migrations.AddField(
            model_name='locationanalysis',
            name='public_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32),
            preserve_default=False,
        ),
        # Step 2: Populate existing rows
        migrations.RunPython(generate_public_ids, migrations.RunPython.noop),
        # Step 3: Add unique constraint
        migrations.AlterField(
            model_name='locationanalysis',
            name='public_id',
            field=models.CharField(blank=True, db_index=True, max_length=32, unique=True),
        ),
    ]
