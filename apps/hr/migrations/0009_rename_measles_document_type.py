from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0008_workgroup_auth_group'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeedocumentversion',
            name='document_type',
            field=models.CharField(
                choices=[
                    ('application', 'Application / Bewerbung'),
                    ('cv', 'Curriculum Vitae / Lebenslauf'),
                    ('latest_degree_certificate', 'Latest Degree Certificate / Zeugnis des letzten Abschlusses'),
                    ('scan_of_contract', 'Scan of Contract / Vertragsscan'),
                    ('profile_picture', 'Profile Picture / Profilbild'),
                ],
                max_length=30,
                verbose_name='Document Type',
            ),
        ),
    ]