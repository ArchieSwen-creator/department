from django.db import models
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_countries.fields import CountryField
from django.conf import settings
from django.contrib.auth.models import User  # Add this import


# ============== LIBERIA COUNTIES CHOICES ==============
LIBERIA_COUNTIES = [
    ("bomi", "Bomi"),
    ("bong", "Bong"),
    ("gbarpolu", "Gbarpolu"),
    ("grand_bassa", "Grand Bassa"),
    ("grand_cape_mount", "Grand Cape Mount"),
    ("grand_gedeh", "Grand Gedeh"),
    ("grand_kru", "Grand Kru"),
    ("lofa", "Lofa"),
    ("margibi", "Margibi"),
    ("maryland", "Maryland"),
    ("montserrado", "Montserrado"),
    ("nimba", "Nimba"),
    ("river_cess", "River Cess"),
    ("river_ghee", "River Gee"),
    ("sinoe", "Sinoe"),
]

# ============== DYNAMIC CHOICES MODELS ==============


class Department(models.Model):
    """Dynamic departments/categories that admin can create"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ["name"]


class CourseCategory(models.Model):
    """Dynamic course categories (formerly Course Type)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Course Categories"


# ============== MAIN MODELS ==============


class Course(models.Model):
    TRACK_CHOICES = [
        ("IR", "International Relations"),
        ("CP", "Comparative Politics"),
        ("LGP", "Liberian Government & Politics"),
        ("ALL", "All Tracks"),
        ("NONE", "No Track"),
    ]

    COURSE_TYPE_CHOICES = [
        ("major", "Major Course"),
        ("minor", "Minor Course"),
        ("elective", "Elective Course"),
        ("required", "Required Core"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    credits = models.IntegerField()
    course_type = models.CharField(max_length=20, choices=COURSE_TYPE_CHOICES)
    track = models.CharField(
        max_length=20, choices=TRACK_CHOICES, default="ALL"
    )  # Which student track this course belongs to
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="courses",
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        CourseCategory, on_delete=models.CASCADE, related_name="courses"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.title}"

    class Meta:
        ordering = ["code"]


class Teacher(models.Model):
    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    RELIGION_CHOICES = [
        ("Christianity", "Christianity"),
        ("Islam", "Islam"),
        ("Traditional", "Traditional African Religion"),
        ("Other", "Other"),
        ("None", "None"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="teachers"
    )
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    # New fields
    nationality = CountryField(blank_label="(select country)", blank=True, null=True)
    county = models.CharField(
        max_length=50,
        choices=LIBERIA_COUNTIES,
        blank=True,
        null=True,
        help_text="County of origin in Liberia",
    )
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, blank=True, null=True
    )
    religion = models.CharField(
        max_length=20, choices=RELIGION_CHOICES, blank=True, null=True
    )
    date_of_birth = models.DateField(blank=True, null=True)

    photo = models.ImageField(upload_to="teachers/", blank=True, null=True)
    photo_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.teacher_id} - {self.name}"

    class Meta:
        ordering = ["name"]


class Student(models.Model):
    TRACK_CHOICES = [
        ("IR", "International Relations"),
        ("CP", "Comparative Politics"),
        ("LGP", "Liberian Government & Politics"),
    ]

    PROGRAM_TYPE_CHOICES = [
        ("major", "Major"),
        ("minor", "Minor"),
    ]

    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    RELIGION_CHOICES = [
        ("Christianity", "Christianity"),
        ("Islam", "Islam"),
        ("Traditional", "Traditional African Religion"),
        ("Other", "Other"),
        ("None", "None"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    year = models.IntegerField()

    # New fields
    program_type = models.CharField(
        max_length=10,
        choices=PROGRAM_TYPE_CHOICES,
        default="major",
        help_text="Whether student is majoring or minoring in the department",
    )
    nationality = CountryField(blank_label="(select country)", blank=True, null=True)
    county = models.CharField(
        max_length=50,
        choices=LIBERIA_COUNTIES,
        blank=True,
        null=True,
        help_text="County of origin in Liberia",
    )
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, blank=True, null=True
    )
    religion = models.CharField(
        max_length=20, choices=RELIGION_CHOICES, blank=True, null=True
    )
    date_of_birth = models.DateField(blank=True, null=True)

    track = models.CharField(
        max_length=20, choices=TRACK_CHOICES, blank=True, null=True
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="students", null=True
    )
    completed_courses = models.JSONField(default=dict)  # Stores {course_id: grade}
    status = models.CharField(
        max_length=20, default="active"
    )  # active, graduated, suspended
    photo = models.ImageField(upload_to="students/", blank=True, null=True)
    photo_url = models.URLField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    enrollment_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student_id} - {self.name}"

    class Meta:
        ordering = ["name"]


class StudentMinor(models.Model):
    """Track which minor courses a student is taking"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="minor_courses"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, limit_choices_to={"course_type": "minor"}
    )
    grade = models.CharField(max_length=2, blank=True, null=True)
    semester = models.CharField(
        max_length=10, blank=True, null=True
    )  # Will be populated from GradeRecord
    year = models.IntegerField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "course"]
        ordering = ["-year", "-semester"]


class StudentElective(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="electives"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, limit_choices_to={"course_type": "elective"}
    )
    grade = models.CharField(max_length=2, blank=True, null=True)
    semester = models.CharField(max_length=10, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "course"]
        ordering = ["-year", "-semester"]

    def __str__(self):
        return f"{self.student.name} - {self.course.code}"


class GradeRecord(models.Model):
    """Enhanced grade tracking with semester and date information"""

    SEMESTER_CHOICES = [
        ("semester1", "Semester 1"),
        ("semester2", "Semester 2"),
    ]

    GRADE_CHOICES = [
        ("A", "A"),
        ("A-", "A-"),
        ("B+", "B+"),
        ("B", "B"),
        ("B-", "B-"),
        ("C+", "C+"),
        ("C", "C"),
        ("D", "D"),
        ("F", "F"),
        ("IP", "In Progress"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="grade_records"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="grade_records"
    )
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    year = models.IntegerField()
    date_recorded = models.DateField(default=timezone.now)
    is_completed = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "course", "semester", "year"]
        ordering = ["-year", "-semester", "-date_recorded"]

    def __str__(self):
        return f"{self.student.student_id} - {self.course.code} - {self.semester} {self.year} - {self.grade}"


class TeacherAssignment(models.Model):
    SEMESTER_CHOICES = [
        ("semester1", "Semester 1"),
        ("semester2", "Semester 2"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="assignments"
    )
    courses = models.ManyToManyField(Course, related_name="teacher_assignments")
    semester = models.CharField(
        max_length=10,
        choices=SEMESTER_CHOICES,
        default="semester1",
    )
    year = models.IntegerField(default=timezone.now().year)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["teacher", "semester", "year"]
        ordering = ["-year", "-semester"]

    def __str__(self):
        return f"{self.teacher.name} - {self.semester} {self.year}"


class LibraryBook(models.Model):
    TRACK_CHOICES = [
        ("ALL", "All Tracks"),
        ("IR", "International Relations"),
        ("CP", "Comparative Politics"),
        ("LGP", "Liberian Government & Politics"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    category = models.ForeignKey(
        CourseCategory, on_delete=models.CASCADE, related_name="books", null=True
    )
    track = models.CharField(max_length=20, choices=TRACK_CHOICES, default="ALL")
    description = models.TextField()
    pdf_file = models.FileField(upload_to="library/", blank=True, null=True)
    pdf_url = models.URLField(blank=True, null=True)
    cover_image = models.ImageField(upload_to="library/covers/", blank=True, null=True)
    cover_color = models.CharField(max_length=20, default="bg-blue-900")
    uploaded_by = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    download_count = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["title"]


class DepartmentDocument(models.Model):
    DOCUMENT_TYPES = [
        ("pdf", "PDF"),
        ("word", "Word Document"),
        ("image", "Image"),
    ]

    TRACK_CHOICES = [
        ("ALL", "All Tracks"),
        ("IR", "International Relations"),
        ("CP", "Comparative Politics"),
        ("LGP", "Liberian Government & Politics"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPES)
    track = models.CharField(max_length=20, choices=TRACK_CHOICES, default="ALL")
    file = models.FileField(upload_to="documents/")
    file_size = models.CharField(max_length=20, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)  # Free text field
    uploaded_by = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    download_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            # Calculate file size
            size = self.file.size
            if size < 1024:
                self.file_size = f"{size} B"
            elif size < 1024 * 1024:
                self.file_size = f"{size / 1024:.1f} KB"
            else:
                self.file_size = f"{size / (1024 * 1024):.1f} MB"
        super().save(*args, **kwargs)


# Add these fields to your SystemSettings model in models.py


class SystemSettings(models.Model):
    """Model for dynamic system settings like logo"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site_logo = models.ImageField(upload_to="settings/", blank=True, null=True)
    site_name = models.CharField(max_length=100, default="Political Science")
    institution_name = models.CharField(max_length=200, default="University of Liberia")
    favicon = models.ImageField(upload_to="settings/", blank=True, null=True)
    primary_color = models.CharField(max_length=20, default="#2563eb")
    secondary_color = models.CharField(max_length=20, default="#64748b")

    # NEW FIELDS for logo and signature
    department_logo = models.ImageField(upload_to="settings/", blank=True, null=True)
    chairman_signature = models.ImageField(
        upload_to="signatures/", blank=True, null=True
    )
    chairman_name = models.CharField(
        max_length=200, default="Assistant Professor, Richmond S. Anderson"
    )
    chairman_title = models.CharField(max_length=200, default="Department Chair")

    # JSON field for any additional settings
    additional_settings = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"


# ============== USER ROLE MODEL ==============
class UserRole(models.Model):
    """User roles for the system - links Django users to application roles"""

    ROLE_CHOICES = [
        ("chairman", "Chairman"),  # Overall admin - full access
        ("teacher", "Record Officer"),  # Manages grades and assignments
        ("clearing", "Clearing Officer"),  # Handles degree audits
        ("assistant", "Administrative Assistant"),  # Department admin
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_role"
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="teacher",
        help_text="User's role in the system",
    )

    # Permissions as JSON field - stores which menus this role can access
    permissions = models.JSONField(
        default=dict, blank=True, help_text="JSON object containing menu permissions"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    class Meta:
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        ordering = ["user__username"]


# ============== PASSWORD RESET MODEL ==============
class PasswordReset(models.Model):
    """Track password reset requests - for chairman to reset user passwords"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_resets",
    )
    reset_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="password_resets_initiated",
    )
    new_password = models.CharField(
        max_length=128, blank=True, null=True
    )  # Store hashed password
    was_successful = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reset_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
