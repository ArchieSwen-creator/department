from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import (
    Department,
    CourseCategory,
    Course,
    Teacher,
    Student,
    StudentMinor,
    StudentElective,
    TeacherAssignment,
    LibraryBook,
    DepartmentDocument,
    SystemSettings,
    GradeRecord,
    UserRole,
)


# ============== INLINE ADMIN FOR USER ROLE ==============
class UserRoleInline(admin.StackedInline):
    """Inline admin for UserRole to display with User"""

    model = UserRole
    can_delete = False
    verbose_name_plural = "User Role"
    fk_name = "user"
    fields = ("role", "permissions", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


# ============== CUSTOM USER ADMIN ==============
class CustomUserAdmin(UserAdmin):
    """Extend UserAdmin to include UserRole"""

    inlines = (UserRoleInline,)
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "get_user_role",
    )
    list_select_related = ("user_role",)

    def get_user_role(self, instance):
        """Display user role in user list"""
        try:
            return instance.user_role.get_role_display()
        except UserRole.DoesNotExist:
            return "No Role"

    get_user_role.short_description = "Role"
    get_user_role.admin_order_field = "user_role__role"


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ============== USER ROLE ADMIN ==============
@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    """Admin configuration for UserRole model"""

    list_display = (
        "user",
        "get_role_display",
        "permissions_summary",
        "created_at",
        "updated_at",
    )
    list_filter = ("role", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    readonly_fields = ("created_at", "updated_at", "permissions_display")
    fieldsets = (
        ("User Information", {"fields": ("user", "role")}),
        (
            "Permissions",
            {
                "fields": ("permissions", "permissions_display"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def permissions_summary(self, obj):
        """Show a summary of permissions"""
        if not obj.permissions:
            return "No permissions set"

        # Count how many permissions are True
        enabled = sum(1 for v in obj.permissions.values() if v)
        total = len(obj.permissions)
        return f"{enabled}/{total} permissions enabled"

    permissions_summary.short_description = "Permissions"

    def permissions_display(self, obj):
        """Display permissions in a readable format"""
        if not obj.permissions:
            return "No permissions configured"

        html = '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">'
        for key, value in sorted(obj.permissions.items()):
            color = "green" if value else "red"
            icon = "✓" if value else "✗"
            html += f'<div style="padding: 5px; border: 1px solid #ddd; border-radius: 4px;">'
            html += f'<span style="color: {color}; font-weight: bold;">{icon}</span> '
            html += f'<span style="margin-left: 5px;">{key.replace("-", " ").title()}</span>'
            html += "</div>"
        html += "</div>"
        return format_html(html)

    permissions_display.short_description = "Permissions Overview"


# ============== DEPARTMENT ADMIN ==============
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin configuration for Department model"""

    list_display = (
        "code",
        "name",
        "course_count",
        "teacher_count",
        "student_count",
        "created_at",
    )
    search_fields = ("code", "name", "description")
    list_filter = ("created_at",)
    readonly_fields = ("created_at", "course_count", "teacher_count", "student_count")
    fieldsets = (
        ("Department Information", {"fields": ("code", "name", "description")}),
        (
            "Statistics",
            {
                "fields": ("course_count", "teacher_count", "student_count"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )

    def course_count(self, obj):
        """Count courses in this department"""
        return obj.courses.count()

    course_count.short_description = "Courses"

    def teacher_count(self, obj):
        """Count teachers in this department"""
        return obj.teachers.count()

    teacher_count.short_description = "Teachers"

    def student_count(self, obj):
        """Count students in this department"""
        return obj.students.count()

    student_count.short_description = "Students"


# ============== COURSE CATEGORY ADMIN ==============
@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    """Admin configuration for CourseCategory model"""

    list_display = ("code", "name", "is_active", "course_count", "created_at")
    search_fields = ("code", "name", "description")
    list_filter = ("is_active", "created_at")
    readonly_fields = ("created_at", "course_count")
    fieldsets = (
        (
            "Category Information",
            {"fields": ("code", "name", "description", "is_active")},
        ),
        (
            "Statistics",
            {
                "fields": ("course_count",),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )

    def course_count(self, obj):
        """Count courses in this category"""
        return obj.courses.count()

    course_count.short_description = "Courses"


# ============== COURSE ADMIN ==============
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """Admin configuration for Course model"""

    list_display = (
        "code",
        "title",
        "credits",
        "course_type",
        "track",
        "department",
        "category",
        "is_active",
    )
    search_fields = ("code", "title")
    list_filter = ("course_type", "track", "is_active", "department", "category")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Course Information",
            {
                "fields": (
                    "code",
                    "title",
                    "credits",
                    "course_type",
                    "track",
                    "is_active",
                )
            },
        ),
        ("Relationships", {"fields": ("department", "category")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


# ============== TEACHER ADMIN ==============
@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    """Admin configuration for Teacher model"""

    list_display = (
        "teacher_id",
        "name",
        "email",
        "department",
        "gender",
        "is_active",
        "assignment_count",
    )
    search_fields = ("teacher_id", "name", "email", "phone")
    list_filter = ("is_active", "gender", "religion", "nationality", "department")
    readonly_fields = ("created_at", "updated_at", "assignment_count", "photo_preview")
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("teacher_id", "name", "email", "phone", "is_active")},
        ),
        ("Department", {"fields": ("department",)}),
        (
            "Demographics",
            {
                "fields": (
                    "nationality",
                    "county",
                    "gender",
                    "religion",
                    "date_of_birth",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Photo",
            {
                "fields": ("photo", "photo_url", "photo_preview"),
                "classes": ("collapse",),
            },
        ),
        (
            "Statistics",
            {
                "fields": ("assignment_count",),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def photo_preview(self, obj):
        """Show photo preview in admin"""
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.photo.url,
            )
        elif obj.photo_url:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.photo_url,
            )
        return "No photo"

    photo_preview.short_description = "Photo Preview"

    def assignment_count(self, obj):
        """Count assignments for this teacher"""
        return obj.assignments.count()

    assignment_count.short_description = "Assignments"


# ============== STUDENT ADMIN ==============
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """Admin configuration for Student model"""

    list_display = (
        "student_id",
        "name",
        "year",
        "program_type",
        "track",
        "status",
        "progress_percent",
    )
    search_fields = ("student_id", "name", "email")
    list_filter = ("program_type", "track", "status", "gender", "religion", "year")
    readonly_fields = (
        "created_at",
        "updated_at",
        "progress_percent",
        "cgpa_display",
        "photo_preview",
    )
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("student_id", "name", "email", "phone", "status")},
        ),
        (
            "Academic Information",
            {"fields": ("year", "program_type", "track", "department")},
        ),
        (
            "Demographics",
            {
                "fields": (
                    "nationality",
                    "county",
                    "gender",
                    "religion",
                    "date_of_birth",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Photo",
            {
                "fields": ("photo", "photo_url", "photo_preview"),
                "classes": ("collapse",),
            },
        ),
        (
            "Academic Progress",
            {
                "fields": ("completed_courses", "progress_percent", "cgpa_display"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("enrollment_date", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def photo_preview(self, obj):
        """Show photo preview in admin"""
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.photo.url,
            )
        elif obj.photo_url:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.photo_url,
            )
        return "No photo"

    photo_preview.short_description = "Photo Preview"

    def progress_percent(self, obj):
        """Calculate and display progress percentage"""
        # This would need the calculate_progress function
        # For admin display, we'll just show a placeholder or call a method
        return "Call from views"

    progress_percent.short_description = "Progress"

    def cgpa_display(self, obj):
        """Display CGPA"""
        # This would need the calculate_cgpa function
        return "Call from views"

    cgpa_display.short_description = "CGPA"


# ============== STUDENT MINOR ADMIN ==============
@admin.register(StudentMinor)
class StudentMinorAdmin(admin.ModelAdmin):
    """Admin configuration for StudentMinor model"""

    list_display = ("student", "course", "grade", "semester", "year", "completed")
    list_filter = ("completed", "semester", "year")
    search_fields = (
        "student__name",
        "student__student_id",
        "course__code",
        "course__title",
    )
    readonly_fields = ("created_at", "updated_at")


# ============== STUDENT ELECTIVE ADMIN ==============
@admin.register(StudentElective)
class StudentElectiveAdmin(admin.ModelAdmin):
    """Admin configuration for StudentElective model"""

    list_display = ("student", "course", "grade", "semester", "year", "completed")
    list_filter = ("completed", "semester", "year")
    search_fields = (
        "student__name",
        "student__student_id",
        "course__code",
        "course__title",
    )
    readonly_fields = ("created_at", "updated_at")


# ============== TEACHER ASSIGNMENT ADMIN ==============
@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    """Admin configuration for TeacherAssignment model"""

    list_display = ("teacher", "semester", "year", "course_count", "created_at")
    list_filter = ("semester", "year")
    search_fields = ("teacher__name", "teacher__teacher_id")
    readonly_fields = ("created_at", "updated_at", "course_list")
    filter_horizontal = ("courses",)

    def course_count(self, obj):
        """Count courses in this assignment"""
        return obj.courses.count()

    course_count.short_description = "Courses"

    def course_list(self, obj):
        """List courses in this assignment"""
        courses = obj.courses.all()
        if not courses:
            return "No courses assigned"
        return format_html("<br>".join([f"{c.code} - {c.title}" for c in courses]))

    course_list.short_description = "Assigned Courses"


# ============== GRADE RECORD ADMIN ==============
@admin.register(GradeRecord)
class GradeRecordAdmin(admin.ModelAdmin):
    """Admin configuration for GradeRecord model"""

    list_display = (
        "student",
        "course",
        "grade",
        "semester",
        "year",
        "date_recorded",
        "is_completed",
    )
    list_filter = ("semester", "year", "grade", "is_completed")
    search_fields = (
        "student__name",
        "student__student_id",
        "course__code",
        "course__title",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "date_recorded"


# ============== LIBRARY BOOK ADMIN ==============
@admin.register(LibraryBook)
class LibraryBookAdmin(admin.ModelAdmin):
    """Admin configuration for LibraryBook model"""

    list_display = (
        "title",
        "author",
        "category",
        "track",
        "uploaded_by",
        "uploaded_at",
        "download_count",
        "view_count",
    )
    list_filter = ("track", "category", "uploaded_at")
    search_fields = ("title", "author", "description")
    readonly_fields = ("uploaded_at", "download_count", "view_count", "pdf_preview")
    fieldsets = (
        (
            "Book Information",
            {"fields": ("title", "author", "description", "category", "track")},
        ),
        (
            "Files",
            {
                "fields": (
                    "pdf_file",
                    "pdf_url",
                    "cover_image",
                    "cover_color",
                    "pdf_preview",
                ),
            },
        ),
        (
            "Upload Information",
            {
                "fields": (
                    "uploaded_by",
                    "uploaded_at",
                    "download_count",
                    "view_count",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def pdf_preview(self, obj):
        """Show PDF preview link"""
        if obj.pdf_file:
            return format_html(
                '<a href="{}" target="_blank">View PDF</a>', obj.pdf_file.url
            )
        elif obj.pdf_url:
            return format_html('<a href="{}" target="_blank">View PDF</a>', obj.pdf_url)
        return "No PDF available"

    pdf_preview.short_description = "PDF Preview"


# ============== DEPARTMENT DOCUMENT ADMIN ==============
@admin.register(DepartmentDocument)
class DepartmentDocumentAdmin(admin.ModelAdmin):
    """Admin configuration for DepartmentDocument model"""

    list_display = (
        "title",
        "author",
        "document_type",
        "track",
        "category",
        "file_size",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("document_type", "track", "uploaded_at")
    search_fields = ("title", "author", "description", "category")
    readonly_fields = ("uploaded_at", "updated_at", "download_count", "file_preview")
    fieldsets = (
        (
            "Document Information",
            {
                "fields": (
                    "title",
                    "author",
                    "description",
                    "category",
                    "document_type",
                    "track",
                )
            },
        ),
        (
            "File",
            {
                "fields": ("file", "file_size", "file_preview"),
            },
        ),
        (
            "Upload Information",
            {
                "fields": (
                    "uploaded_by",
                    "uploaded_at",
                    "updated_at",
                    "download_count",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def file_preview(self, obj):
        """Show file preview link"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">View File</a>', obj.file.url
            )
        return "No file"

    file_preview.short_description = "File Preview"


# ============== SYSTEM SETTINGS ADMIN ==============
@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """Admin configuration for SystemSettings model"""

    list_display = ("site_name", "institution_name", "updated_at")
    fieldsets = (
        ("Site Information", {"fields": ("site_name", "institution_name")}),
        (
            "Appearance",
            {
                "fields": ("site_logo", "favicon", "primary_color", "secondary_color"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("updated_at",),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        """Only allow one instance of SystemSettings"""
        return not SystemSettings.objects.exists()
