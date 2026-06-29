# profiles/migrations/0004_increase_profile_picture_length.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('profiles', '0003_alter_parentprofile_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parentprofile',
            name='profile_picture',
            field=models.ImageField(blank=True, max_length=500, null=True, upload_to='profiles/pictures/'),
        ),
        migrations.AlterField(
            model_name='studentprofile',
            name='profile_picture',
            field=models.ImageField(blank=True, max_length=500, null=True, upload_to='profiles/pictures/'),
        ),
        migrations.AlterField(
            model_name='teacherprofile',
            name='profile_picture',
            field=models.ImageField(blank=True, max_length=500, null=True, upload_to='profiles/pictures/'),
        ),
    ]