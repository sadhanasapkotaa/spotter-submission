from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Enable PostGIS in every environment (managed DBs don't ship it enabled)."""

    initial = True
    dependencies = []
    operations = [CreateExtension("postgis")]
