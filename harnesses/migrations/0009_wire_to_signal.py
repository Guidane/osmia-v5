from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('harnesses', '0008_end_side'),
    ]

    operations = [
        migrations.AddField(
            model_name='wire',
            name='to_signal',
            field=models.CharField(blank=True, max_length=100, verbose_name='signal at its other end'),
        ),
    ]
