# Generated for leave_management app

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('profiles', '0002_parentstudentmapping'),
        ('tenants', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('applicant_role', models.CharField(choices=[('Student', 'Student'), ('Teacher', 'Teacher')], max_length=10)),
                ('leave_type', models.CharField(choices=[('Sick', 'Sick'), ('Casual', 'Casual'), ('Emergency', 'Emergency'), ('Other', 'Other')], default='Casual', max_length=20)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('reason', models.TextField()),
                ('attachment', models.FileField(blank=True, max_length=500, null=True, upload_to='leave_attachments/')),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected'), ('Cancelled', 'Cancelled')], default='Pending', max_length=10)),
                ('applied_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_remarks', models.CharField(blank=True, max_length=255, null=True)),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s_set', to='tenants.school')),
                ('student', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='leave_requests', to='profiles.studentprofile')),
                ('teacher', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='leave_requests', to='profiles.teacherprofile')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='leave_requests_reviewed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-applied_at'],
            },
        ),
        migrations.AddIndex(
            model_name='leaverequest',
            index=models.Index(fields=['school', 'applicant_role', 'status'], name='leave_man_l_school__b1a5c1_idx'),
        ),
        migrations.AddIndex(
            model_name='leaverequest',
            index=models.Index(fields=['student', 'status'], name='leave_man_l_student_4f2b29_idx'),
        ),
        migrations.AddIndex(
            model_name='leaverequest',
            index=models.Index(fields=['teacher', 'status'], name='leave_man_l_teacher_7d3a9e_idx'),
        ),
    ]
