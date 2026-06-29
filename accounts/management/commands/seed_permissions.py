# accounts/management/commands/seed_permissions.py
from django.core.management.base import BaseCommand
from accounts.models import Permission, Role
from tenants.models import School

class Command(BaseCommand):
    help = 'Seed default permissions and roles for the system'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding permissions and roles...')
        
        # Create permissions
        permissions = [
            # Student Permissions
            {'name': 'View Own Profile', 'codename': 'student.view_profile', 'module': 'Student'},
            {'name': 'Update Own Profile', 'codename': 'student.update_profile', 'module': 'Student'},
            {'name': 'View Own Grades', 'codename': 'student.view_grades', 'module': 'Student'},
            {'name': 'View Own Attendance', 'codename': 'student.view_attendance', 'module': 'Student'},
            {'name': 'View Own Assignments', 'codename': 'student.view_assignments', 'module': 'Student'},
            {'name': 'Submit Assignments', 'codename': 'student.submit_assignment', 'module': 'Student'},
            {'name': 'View Own Exams', 'codename': 'student.view_exams', 'module': 'Student'},
            {'name': 'View Dashboard', 'codename': 'student.view_dashboard', 'module': 'Student'},
            
            # Teacher Permissions
            {'name': 'View Class Roster', 'codename': 'teacher.view_roster', 'module': 'Teacher'},
            {'name': 'Mark Attendance', 'codename': 'teacher.mark_attendance', 'module': 'Teacher'},
            {'name': 'View Attendance', 'codename': 'teacher.view_attendance', 'module': 'Teacher'},
            {'name': 'Create Assignments', 'codename': 'teacher.create_assignment', 'module': 'Teacher'},
            {'name': 'View Assignments', 'codename': 'teacher.view_assignments', 'module': 'Teacher'},
            {'name': 'Update Assignments', 'codename': 'teacher.update_assignment', 'module': 'Teacher'},
            {'name': 'Delete Assignments', 'codename': 'teacher.delete_assignment', 'module': 'Teacher'},
            {'name': 'Grade Submissions', 'codename': 'teacher.grade_submission', 'module': 'Teacher'},
            {'name': 'View Submissions', 'codename': 'teacher.view_submissions', 'module': 'Teacher'},
            {'name': 'Create Grades', 'codename': 'teacher.create_grades', 'module': 'Teacher'},
            {'name': 'View All Grades', 'codename': 'teacher.view_all_grades', 'module': 'Teacher'},
            {'name': 'View Own Profile', 'codename': 'teacher.view_profile', 'module': 'Teacher'},
            {'name': 'Update Own Profile', 'codename': 'teacher.update_profile', 'module': 'Teacher'},
            {'name': 'View Dashboard', 'codename': 'teacher.view_dashboard', 'module': 'Teacher'},
            {'name': 'Create Exams', 'codename': 'teacher.create_exams', 'module': 'Teacher'},
            {'name': 'View Exams', 'codename': 'teacher.view_exams', 'module': 'Teacher'},
            
            # Parent Permissions
            {'name': 'View Child Profile', 'codename': 'parent.view_child_profile', 'module': 'Parent'},
            {'name': 'View Child Grades', 'codename': 'parent.view_child_grades', 'module': 'Parent'},
            {'name': 'View Child Attendance', 'codename': 'parent.view_child_attendance', 'module': 'Parent'},
            {'name': 'View Child Assignments', 'codename': 'parent.view_child_assignments', 'module': 'Parent'},
            {'name': 'View Child Exams', 'codename': 'parent.view_child_exams', 'module': 'Parent'},
            {'name': 'View Own Profile', 'codename': 'parent.view_profile', 'module': 'Parent'},
            {'name': 'Update Own Profile', 'codename': 'parent.update_profile', 'module': 'Parent'},
            {'name': 'View Dashboard', 'codename': 'parent.view_dashboard', 'module': 'Parent'},
            
            # Admin Permissions
            {'name': 'Manage Users', 'codename': 'admin.manage_users', 'module': 'Admin'},
            {'name': 'Manage Roles', 'codename': 'admin.manage_roles', 'module': 'Admin'},
            {'name': 'Manage Schools', 'codename': 'admin.manage_schools', 'module': 'Admin'},
            {'name': 'View All Data', 'codename': 'admin.view_all_data', 'module': 'Admin'},
            {'name': 'Manage Academic Years', 'codename': 'admin.manage_academic_years', 'module': 'Admin'},
            {'name': 'Manage Classes', 'codename': 'admin.manage_classes', 'module': 'Admin'},
            {'name': 'Manage Sections', 'codename': 'admin.manage_sections', 'module': 'Admin'},
            {'name': 'Manage Subjects', 'codename': 'admin.manage_subjects', 'module': 'Admin'},
            {'name': 'Manage Enrollments', 'codename': 'admin.manage_enrollments', 'module': 'Admin'},
            {'name': 'View Dashboard', 'codename': 'admin.view_dashboard', 'module': 'Admin'},
        ]

        created_permissions = []
        for perm in permissions:
            obj, created = Permission.objects.get_or_create(
                codename=perm['codename'],
                defaults={
                    'name': perm['name'],
                    'module': perm['module']
                }
            )
            created_permissions.append(obj)
            if created:
                self.stdout.write(f'✅ Created permission: {perm["name"]} ({perm["codename"]})')
            else:
                self.stdout.write(f'⏭️  Permission already exists: {perm["name"]}')

        self.stdout.write(self.style.SUCCESS(f'\n✅ {len(created_permissions)} permissions seeded successfully!'))

        # Create default roles for each school
        schools = School.objects.all()
        
        if not schools.exists():
            self.stdout.write(self.style.WARNING('⚠️  No schools found. Please create a school first.'))
            return

        for school in schools:
            self._create_roles_for_school(school, created_permissions)

        self.stdout.write(self.style.SUCCESS('\n🎉 RBAC setup complete!'))

    def _create_roles_for_school(self, school, permissions):
        """Create default roles for a specific school."""
        
        # Map permission codenames to role names
        role_permissions = {
            'Student': [
                'student.view_profile',
                'student.update_profile',
                'student.view_grades',
                'student.view_attendance',
                'student.view_assignments',
                'student.submit_assignment',
                'student.view_exams',
                'student.view_dashboard',
            ],
            'Teacher': [
                'teacher.view_roster',
                'teacher.mark_attendance',
                'teacher.view_attendance',
                'teacher.create_assignment',
                'teacher.view_assignments',
                'teacher.update_assignment',
                'teacher.delete_assignment',
                'teacher.grade_submission',
                'teacher.view_submissions',
                'teacher.create_grades',
                'teacher.view_all_grades',
                'teacher.view_profile',
                'teacher.update_profile',
                'teacher.view_dashboard',
                'teacher.create_exams',
                'teacher.view_exams',
            ],
            'Parent': [
                'parent.view_child_profile',
                'parent.view_child_grades',
                'parent.view_child_attendance',
                'parent.view_child_assignments',
                'parent.view_child_exams',
                'parent.view_profile',
                'parent.update_profile',
                'parent.view_dashboard',
            ],
            'Admin': [
                'admin.manage_users',
                'admin.manage_roles',
                'admin.manage_schools',
                'admin.view_all_data',
                'admin.manage_academic_years',
                'admin.manage_classes',
                'admin.manage_sections',
                'admin.manage_subjects',
                'admin.manage_enrollments',
                'admin.view_dashboard',
            ],
        }

        for role_name, perm_codenames in role_permissions.items():
            # Get or create role
            role, created = Role.objects.get_or_create(
                school=school,
                name=role_name,
                defaults={'description': f'Default {role_name} role'}
            )
            
            # Add permissions
            role_permissions_list = []
            for codename in perm_codenames:
                try:
                    perm = Permission.objects.get(codename=codename)
                    role_permissions_list.append(perm)
                except Permission.DoesNotExist:
                    self.stdout.write(f'⚠️  Permission not found: {codename}')
            
            role.permissions.set(role_permissions_list)
            
            if created:
                self.stdout.write(f'✅ Created role: {role_name} for school {school.name}')
            else:
                self.stdout.write(f'⏭️  Updated role: {role_name} for school {school.name}')