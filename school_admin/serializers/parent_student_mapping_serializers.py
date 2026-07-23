from rest_framework import serializers
from profiles.models import ParentProfile, StudentProfile, ParentStudentMapping


class ParentStudentLinkSerializer(serializers.ModelSerializer):
    """
    Links an existing parent to an existing student using their email /
    enrollment number, rather than internal UUIDs -- this is what makes it
    usable from a plain spreadsheet upload.

    Both the parent and student must already be registered in this school
    (e.g. via the onboarding or bulk-onboarding endpoints) before they can
    be linked.
    """
    parent_email = serializers.EmailField(write_only=True)
    student_enrollment_number = serializers.CharField(write_only=True)

    class Meta:
        model = ParentStudentMapping
        fields = [
            'id',
            'parent_email',
            'student_enrollment_number',
            'relationship',
            'is_primary_contact',
            'can_view_academics',
            'can_pay_fees',
        ]

    def validate(self, attrs):
        school = self.context['request'].user.school
        parent_email = attrs.pop('parent_email')
        enrollment_number = attrs.pop('student_enrollment_number')

        try:
            parent = ParentProfile.objects.get(user__email__iexact=parent_email, school=school)
        except ParentProfile.DoesNotExist:
            raise serializers.ValidationError(
                {"parent_email": f"No parent found with email '{parent_email}' in this school."}
            )

        try:
            student = StudentProfile.objects.get(enrollment_number=enrollment_number, school=school)
        except StudentProfile.DoesNotExist:
            raise serializers.ValidationError(
                {"student_enrollment_number": f"No student found with enrollment number '{enrollment_number}'."}
            )

        if ParentStudentMapping.objects.filter(parent=parent, student=student, school=school).exists():
            raise serializers.ValidationError("This parent is already linked to this student.")

        attrs['parent'] = parent
        attrs['student'] = student
        attrs['school'] = school
        return attrs

    def create(self, validated_data):
        return ParentStudentMapping.objects.create(**validated_data)