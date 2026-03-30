# Add these with your other imports at the top of views.py
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import mimetypes
from django.shortcuts import render, redirect
from django.contrib.auth import logout, login, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.conf import settings as django_settings
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
    LIBERIA_COUNTIES,
    UserRole,
    PasswordReset,
)

import json
import uuid
import os
from datetime import datetime
import mimetypes
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.lib.fonts import addMapping
import tempfile
import calendar
from collections import defaultdict
from django_countries import countries


# ============== EMAIL HELPER FUNCTION ==============
def send_custom_email(subject, message, recipient_list, attachment_path=None, attachment_name=None, html_message=None, cc_list=None):
    """
    Send custom email with optional file attachment and custom message
    
    Args:
        subject: Email subject
        message: Plain text message (can include custom user message)
        recipient_list: List of recipient emails
        attachment_path: Path to file to attach (optional)
        attachment_name: Custom name for attachment (optional)
        html_message: HTML version of message (optional)
        cc_list: List of CC recipients (optional)
    """
    try:
        if html_message:
            email = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipient_list if isinstance(recipient_list, list) else [recipient_list],
                cc=cc_list or [],
            )
            email.attach_alternative(html_message, "text/html")
        else:
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipient_list if isinstance(recipient_list, list) else [recipient_list],
                cc=cc_list or [],
            )
        
        # Attach file if provided
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as file:
                file_name = attachment_name or os.path.basename(attachment_path)
                email.attach(file_name, file.read())
        
        # Send email
        email.send(fail_silently=False)
        return True, "Email sent successfully"
        
    except Exception as e:
        return False, str(e)

# ============== LOGOUT VIEW ==============
def logout_view(request):
    """Log out user and redirect to login page"""
    logout(request)
    return redirect("/login/")


# ============== LOGIN VIEW ==============
def login_view(request):
    """Custom login view"""
    if request.method == "GET":
        # Return simple login page or redirect to admin
        return render(request, "login.html")

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get("username")
            password = data.get("password")

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)

                # Get user role
                try:
                    role = UserRole.objects.get(user=user)
                    role_name = role.role
                    role_display = role.get_role_display()
                except UserRole.DoesNotExist:
                    # Create default role if not exists
                    role = UserRole.objects.create(
                        user=user,
                        role="teacher" if not user.is_superuser else "chairman",
                    )
                    role_name = role.role
                    role_display = role.get_role_display()

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Login successful",
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                            "email": user.email,
                            "role": role_name,
                            "role_display": role_display,
                            "is_superuser": user.is_superuser,
                        },
                    }
                )
            else:
                return JsonResponse(
                    {"success": False, "error": "Invalid username or password"},
                    status=401,
                )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


def logout_view(request):
    """Log out user and redirect to login page"""
    logout(request)
    return redirect("/login/")


# ============== PASSWORD MANAGEMENT ==============
@login_required
@require_http_methods(["POST"])
@csrf_exempt
def change_own_password(request):
    """Allow any logged-in user to change their own password (requires current password)"""
    try:
        data = json.loads(request.body)
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password")

        if not current_password or not new_password or not confirm_password:
            return JsonResponse({"error": "All fields are required"}, status=400)

        if new_password != confirm_password:
            return JsonResponse({"error": "New passwords do not match"}, status=400)

        if len(new_password) < 8:
            return JsonResponse(
                {"error": "Password must be at least 8 characters"}, status=400
            )

        # Verify current password
        if not request.user.check_password(current_password):
            return JsonResponse({"error": "Current password is incorrect"}, status=400)

        # Change password
        request.user.set_password(new_password)
        request.user.save()

        # Update session to prevent logout
        update_session_auth_hash(request, request.user)

        # Log password change
        PasswordReset.objects.create(
            user=request.user,
            reset_by=request.user,
            new_password=make_password(new_password),
            was_successful=True,
            reset_at=timezone.now(),
        )

        return JsonResponse({"message": "Password changed successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def get_all_users_for_chairman(request):
    """Get all users for password reset (Chairman only) - No old password required"""
    try:
        # Check if current user is chairman (admin)
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        users = (
            User.objects.filter(is_active=True)
            .exclude(is_superuser=True)
            .select_related("user_role")
        )
        result = []

        for user in users:
            # Skip the chairman themselves from the list
            if user.id == request.user.id:
                continue

            role_obj = getattr(user, "user_role", None)

            # Get last password reset
            last_reset = (
                PasswordReset.objects.filter(user=user, was_successful=True)
                .order_by("-created_at")
                .first()
            )

            # Get display name
            full_name = f"{user.first_name} {user.last_name}".strip()
            if not full_name:
                full_name = user.username

            result.append(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "full_name": full_name,
                    "email": user.email,
                    "role": role_obj.role if role_obj else "teacher",
                    "role_display": (
                        role_obj.get_role_display() if role_obj else "Record Officer"
                    ),
                    "last_password_reset": (
                        last_reset.reset_at.strftime("%Y-%m-%d %H:%M")
                        if last_reset
                        else "Never"
                    ),
                    "created_at": user.date_joined.strftime("%Y-%m-%d"),
                    "is_active": user.is_active,
                }
            )

        return JsonResponse(result, safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def get_user_details_for_chairman(request, user_id):
    """Get details for a specific user (Chairman only)"""
    try:
        # Check if current user is chairman (admin)
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        role_obj = getattr(user, "user_role", None)

        # Get password reset history
        reset_history = []
        for reset in PasswordReset.objects.filter(user=user).order_by("-created_at")[
            :5
        ]:
            reset_by_name = reset.reset_by.username if reset.reset_by else "System"
            reset_history.append(
                {
                    "id": str(reset.id),
                    "reset_by": reset_by_name,
                    "created_at": reset.created_at.strftime("%Y-%m-%d %H:%M"),
                    "reset_at": (
                        reset.reset_at.strftime("%Y-%m-%d %H:%M")
                        if reset.reset_at
                        else None
                    ),
                    "was_successful": reset.was_successful,
                }
            )

        full_name = f"{user.first_name} {user.last_name}".strip()
        if not full_name:
            full_name = user.username

        return JsonResponse(
            {
                "id": str(user.id),
                "username": user.username,
                "full_name": full_name,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "role": role_obj.role if role_obj else "teacher",
                "role_display": (
                    role_obj.get_role_display() if role_obj else "Record Officer"
                ),
                "date_joined": user.date_joined.strftime("%Y-%m-%d"),
                "last_login": (
                    user.last_login.strftime("%Y-%m-%d %H:%M")
                    if user.last_login
                    else None
                ),
                "is_active": user.is_active,
                "reset_history": reset_history,
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def reset_user_password_by_chairman(request):
    """Reset another user's password (Chairman only) - NO OLD PASSWORD REQUIRED"""
    try:
        # Check if current user is chairman (admin)
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        data = json.loads(request.body)
        user_id = data.get("user_id")
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password")

        if not user_id or not new_password or not confirm_password:
            return JsonResponse(
                {"error": "User ID and new password are required"}, status=400
            )

        if new_password != confirm_password:
            return JsonResponse({"error": "Passwords do not match"}, status=400)

        if len(new_password) < 8:
            return JsonResponse(
                {"error": "Password must be at least 8 characters"}, status=400
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        # Don't allow resetting chairman's own password through this endpoint
        if user.id == request.user.id:
            return JsonResponse(
                {"error": "Use 'Change Password' option to change your own password"},
                status=400,
            )

        # Set new password (NO OLD PASSWORD REQUIRED)
        user.set_password(new_password)
        user.save()

        # Log the password reset
        PasswordReset.objects.create(
            user=user,
            reset_by=request.user,
            new_password=make_password(new_password),
            was_successful=True,
            reset_at=timezone.now(),
        )

        return JsonResponse(
            {
                "message": f"Password for {user.username} has been reset successfully",
                "user": user.username,
            }
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def admin_dashboard(request):
    """Render the main admin dashboard template with settings"""
    settings = SystemSettings.objects.first()
    context = {
        "settings": settings,
        "MEDIA_URL": django_settings.MEDIA_URL,  # Use Django's settings
    }
    return render(request, "admin.html", context)


# ============== SYSTEM SETTINGS API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def system_settings_list(request):
    """Get or update system settings"""
    if request.method == "GET":
        settings = SystemSettings.objects.first()
        if settings:
            return JsonResponse(
                {
                    "id": settings.id,
                    "site_name": settings.site_name,
                    "institution_name": settings.institution_name,
                    "logo_url": settings.site_logo.url if settings.site_logo else None,
                    "primary_color": settings.primary_color,
                    "secondary_color": settings.secondary_color,
                }
            )
        return JsonResponse({})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            settings, created = SystemSettings.objects.get_or_create(id=1)

            settings.site_name = data.get("site_name", settings.site_name)
            settings.institution_name = data.get(
                "institution_name", settings.institution_name
            )
            settings.primary_color = data.get("primary_color", settings.primary_color)
            settings.secondary_color = data.get(
                "secondary_color", settings.secondary_color
            )
            settings.save()

            return JsonResponse(
                {
                    "message": "Settings updated successfully",
                    "site_name": settings.site_name,
                    "institution_name": settings.institution_name,
                }
            )
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def upload_logo(request):
    """Handle logo upload"""
    try:
        logo_file = request.FILES.get("logo")
        if not logo_file:
            return JsonResponse({"error": "No logo file provided"}, status=400)

        # Validate file type
        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/jpg",
            "image/svg+xml",
        ]
        if logo_file.content_type not in allowed_types:
            return JsonResponse(
                {"error": "File must be an image (JPEG, PNG, GIF, SVG)"}, status=400
            )

        # Create settings directory if it doesn't exist
        settings_dir = os.path.join(settings.MEDIA_ROOT, "settings")
        os.makedirs(settings_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logo_{timestamp}.{logo_file.name.split('.')[-1]}"

        # Save file
        fs = FileSystemStorage(location=settings_dir)
        filename = fs.save(filename, logo_file)
        logo_url = f"{settings.MEDIA_URL}settings/{filename}"

        # Update settings
        settings_obj, created = SystemSettings.objects.get_or_create(id=1)
        settings_obj.site_logo = f"settings/{filename}"
        settings_obj.save()

        return JsonResponse(
            {"message": "Logo uploaded successfully", "logo_url": logo_url}
        )

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== DEPARTMENT API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def department_list(request):
    """List all departments or create a new department"""
    if request.method == "GET":
        departments = Department.objects.all().order_by("code")
        result = []
        for dept in departments:
            # Get course counts for each department
            course_count = Course.objects.filter(department=dept).count()
            teacher_count = Teacher.objects.filter(department=dept).count()
            student_count = Student.objects.filter(department=dept).count()

            result.append(
                {
                    "id": dept.id,
                    "code": dept.code,
                    "name": dept.name,
                    "description": dept.description,
                    "course_count": course_count,
                    "teacher_count": teacher_count,
                    "student_count": student_count,
                    "created_at": (
                        dept.created_at.strftime("%Y-%m-%d %H:%M")
                        if dept.created_at
                        else None
                    ),
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            # Check if department with same code exists
            if Department.objects.filter(code=data["code"]).exists():
                return JsonResponse(
                    {"error": "Department code already exists"}, status=400
                )

            # Check if department with same name exists
            if Department.objects.filter(name=data["name"]).exists():
                return JsonResponse(
                    {"error": "Department name already exists"}, status=400
                )

            department = Department.objects.create(
                code=data["code"].upper(),
                name=data["name"],
                description=data.get("description", ""),
            )

            return JsonResponse(
                {"id": department.id, "message": "Department created successfully"}
            )
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def department_detail(request, pk):
    """Get, update, or delete a specific department"""
    try:
        department = Department.objects.get(pk=pk)
    except Department.DoesNotExist:
        return JsonResponse({"error": "Department not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "id": department.id,
                "code": department.code,
                "name": department.name,
                "description": department.description,
                "created_at": (
                    department.created_at.strftime("%Y-%m-%d %H:%M")
                    if department.created_at
                    else None
                ),
            }
        )

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)

            # Check code uniqueness if changed
            if "code" in data and data["code"] != department.code:
                if Department.objects.filter(code=data["code"]).exists():
                    return JsonResponse(
                        {"error": "Department code already exists"}, status=400
                    )
                department.code = data["code"].upper()

            # Check name uniqueness if changed
            if "name" in data and data["name"] != department.name:
                if Department.objects.filter(name=data["name"]).exists():
                    return JsonResponse(
                        {"error": "Department name already exists"}, status=400
                    )
                department.name = data["name"]

            department.description = data.get("description", department.description)
            department.save()

            return JsonResponse({"message": "Department updated successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        # Check if department is in use
        if Course.objects.filter(department=department).exists():
            return JsonResponse(
                {"error": "Cannot delete department with associated courses"},
                status=400,
            )
        if Teacher.objects.filter(department=department).exists():
            return JsonResponse(
                {"error": "Cannot delete department with associated teachers"},
                status=400,
            )
        if Student.objects.filter(department=department).exists():
            return JsonResponse(
                {"error": "Cannot delete department with associated students"},
                status=400,
            )

        department.delete()
        return JsonResponse({"message": "Department deleted successfully"})


# ============== COURSE CATEGORY API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def course_category_list(request):
    """List all course categories or create a new category"""
    if request.method == "GET":
        categories = CourseCategory.objects.all().order_by("code")
        result = []
        for cat in categories:
            # Count courses in this category
            course_count = Course.objects.filter(category=cat).count()

            result.append(
                {
                    "id": cat.id,
                    "code": cat.code,
                    "name": cat.name,
                    "description": cat.description,
                    "is_active": cat.is_active,
                    "course_count": course_count,
                    "created_at": (
                        cat.created_at.strftime("%Y-%m-%d %H:%M")
                        if cat.created_at
                        else None
                    ),
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            # Check if category with same code exists
            if CourseCategory.objects.filter(code=data["code"]).exists():
                return JsonResponse(
                    {"error": "Category code already exists"}, status=400
                )

            # Check if category with same name exists
            if CourseCategory.objects.filter(name=data["name"]).exists():
                return JsonResponse(
                    {"error": "Category name already exists"}, status=400
                )

            category = CourseCategory.objects.create(
                code=data["code"].lower(),
                name=data["name"],
                description=data.get("description", ""),
                is_active=data.get("is_active", True),
            )

            return JsonResponse(
                {"id": category.id, "message": "Course category created successfully"}
            )
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def course_category_detail(request, pk):
    """Get, update, or delete a specific course category"""
    try:
        category = CourseCategory.objects.get(pk=pk)
    except CourseCategory.DoesNotExist:
        return JsonResponse({"error": "Course category not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "id": category.id,
                "code": category.code,
                "name": category.name,
                "description": category.description,
                "is_active": category.is_active,
                "created_at": (
                    category.created_at.strftime("%Y-%m-%d %H:%M")
                    if category.created_at
                    else None
                ),
            }
        )

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)

            # Check code uniqueness if changed
            if "code" in data and data["code"] != category.code:
                if CourseCategory.objects.filter(code=data["code"]).exists():
                    return JsonResponse(
                        {"error": "Category code already exists"}, status=400
                    )
                category.code = data["code"].lower()

            # Check name uniqueness if changed
            if "name" in data and data["name"] != category.name:
                if CourseCategory.objects.filter(name=data["name"]).exists():
                    return JsonResponse(
                        {"error": "Category name already exists"}, status=400
                    )
                category.name = data["name"]

            category.description = data.get("description", category.description)
            category.is_active = data.get("is_active", category.is_active)
            category.save()

            return JsonResponse({"message": "Course category updated successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        # Check if category is in use
        if Course.objects.filter(category=category).exists():
            return JsonResponse(
                {"error": "Cannot delete category with associated courses"}, status=400
            )

        category.delete()
        return JsonResponse({"message": "Course category deleted successfully"})


# ============== DASHBOARD API ==============
@login_required
@require_http_methods(["GET"])
def get_dashboard_data(request):
    """Get comprehensive dashboard statistics"""
    students = Student.objects.all()
    courses = Course.objects.filter(is_active=True)
    teachers = Teacher.objects.filter(is_active=True)

    # Calculate statistics
    total_students = students.count()
    active_students = students.filter(status="active").count()

    # Graduation ready and average completion
    graduation_ready = 0
    total_completion = 0
    student_progress_data = []

    track_distribution = {"IR": 0, "CP": 0, "LGP": 0, "None": 0}
    program_distribution = {"major": 0, "minor": 0}

    for student in students:
        progress = calculate_progress(student)
        total_percent = progress["percent_complete"]
        total_completion += total_percent

        if total_percent >= 95:
            graduation_ready += 1

        # Track distribution
        if student.track == "IR":
            track_distribution["IR"] += 1
        elif student.track == "CP":
            track_distribution["CP"] += 1
        elif student.track == "LGP":
            track_distribution["LGP"] += 1
        else:
            track_distribution["None"] += 1

        # Program distribution
        if student.program_type == "major":
            program_distribution["major"] += 1
        else:
            program_distribution["minor"] += 1

        # Collect progress data for charts
        student_progress_data.append(
            {"name": student.name, "progress": total_percent, "track": student.track}
        )

    avg_completion = (
        round(total_completion / total_students) if total_students > 0 else 0
    )

    # Get recent grades (last 10)
    recent_grades = []
    grade_count = 0

    for student in students.order_by("-updated_at"):
        if grade_count >= 10:
            break

        for course_id, grade in student.completed_courses.items():
            if grade_count >= 10:
                break

            if grade and grade not in ["IP", None]:
                try:
                    course = Course.objects.get(id=course_id)
                    recent_grades.append(
                        {
                            "student": student.name,
                            "student_id": student.student_id,
                            "course": course.code,
                            "course_title": course.title,
                            "grade": grade,
                            "date": student.updated_at.strftime("%Y-%m-%d"),
                        }
                    )
                    grade_count += 1
                except Course.DoesNotExist:
                    continue

    # Get top students by CGPA
    top_students = []
    for student in students.filter(status="active", track__isnull=False):
        cgpa = calculate_cgpa(student)
        if cgpa > 0:
            top_students.append(
                {
                    "id": student.id,
                    "name": student.name,
                    "student_id": student.student_id,
                    "cgpa": round(cgpa, 2),
                    "track": student.track,
                    "program_type": student.program_type,
                    "photo_url": (
                        student.photo.url if student.photo else student.photo_url
                    ),
                }
            )

    top_students.sort(key=lambda x: x["cgpa"], reverse=True)
    top_students = top_students[:3]

    # Get deficiencies (D and F grades)
    deficiencies = []
    for student in students:
        for course_id, grade in student.completed_courses.items():
            if grade in ["D", "F"]:
                try:
                    course = Course.objects.get(id=course_id)
                    deficiencies.append(
                        {
                            "student": student.name,
                            "student_id": student.student_id,
                            "course": course.code,
                            "course_title": course.title,
                            "grade": grade,
                        }
                    )
                except Course.DoesNotExist:
                    continue
                if len(deficiencies) >= 5:
                    break
        if len(deficiencies) >= 5:
            break

    data = {
        "total_students": total_students,
        "active_students": active_students,
        "graduation_ready": graduation_ready,
        "avg_completion": avg_completion,
        "courses_offered": courses.count(),
        "total_teachers": teachers.count(),
        "student_growth": 12,
        "ready_this_month": Student.objects.filter(
            status="graduated", updated_at__month=timezone.now().month
        ).count(),
        "track_distribution": track_distribution,
        "program_distribution": program_distribution,
        "top_students": top_students,
        "deficiencies": deficiencies[:5],
        "recent_grades": recent_grades[:5],
    }
    return JsonResponse(data)


# ============== COURSE API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def course_list(request):
    """List all courses or create a new course"""
    if request.method == "GET":
        courses = Course.objects.filter(is_active=True).select_related(
            "department", "category"
        )
        result = []
        for course in courses:
            result.append(
                {
                    "id": course.id,
                    "code": course.code,
                    "title": course.title,
                    "credits": course.credits,
                    "course_type": course.course_type,
                    "track": course.track,
                    "dept": course.department.name if course.department else None,
                    "dept_id": course.department_id,
                    "dept_code": course.department.code if course.department else None,
                    "category": course.category.code if course.category else None,
                    "category_id": course.category_id,
                    "category_name": course.category.name if course.category else None,
                    "is_active": course.is_active,
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            # Log received data for debugging
            print("=" * 50)
            print("Received course data:", data)
            print("=" * 50)

            # Check if course with same code exists
            if Course.objects.filter(code=data["code"]).exists():
                return JsonResponse(
                    {"error": f"Course code '{data['code']}' already exists"},
                    status=400,
                )

            # Get department if provided
            department = None
            if data.get("dept_id"):
                try:
                    department = Department.objects.get(id=data["dept_id"])
                except Department.DoesNotExist:
                    return JsonResponse(
                        {"error": f"Department with id {data['dept_id']} not found"},
                        status=404,
                    )

            # Get category
            try:
                category = CourseCategory.objects.get(id=data["category_id"])
            except CourseCategory.DoesNotExist:
                return JsonResponse(
                    {"error": f"Category with id {data['category_id']} not found"},
                    status=404,
                )

            # Validate course_type is one of the allowed choices
            valid_course_types = ["major", "minor", "elective", "required"]
            if data["course_type"] not in valid_course_types:
                return JsonResponse(
                    {
                        "error": f"Invalid course_type. Must be one of: {', '.join(valid_course_types)}"
                    },
                    status=400,
                )

            # Create course
            course = Course.objects.create(
                code=data["code"],
                title=data["title"],
                credits=data["credits"],
                course_type=data["course_type"],
                track=data.get("track", "ALL"),
                department=department,
                category=category,
                is_active=data.get("is_active", True),
            )

            print(f"Course created successfully: {course.code}")

            return JsonResponse(
                {
                    "id": str(course.id),
                    "message": "Course created successfully",
                    "code": course.code,
                },
                status=201,
            )

        except KeyError as e:
            print(f"Missing field error: {e}")
            return JsonResponse({"error": f"Missing required field: {e}"}, status=400)
        except ValueError as e:
            print(f"Value error: {e}")
            return JsonResponse({"error": f"Invalid value: {e}"}, status=400)
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def course_detail(request, pk):
    """Get, update, or delete a specific course"""
    try:
        course = Course.objects.get(pk=pk)
    except Course.DoesNotExist:
        return JsonResponse({"error": "Course not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "id": course.id,
                "code": course.code,
                "title": course.title,
                "credits": course.credits,
                "course_type": course.course_type,
                "track": course.track,
                "dept_id": course.department_id,
                "dept": course.department.name if course.department else None,
                "category_id": course.category_id,
                "category": course.category.code if course.category else None,
                "is_active": course.is_active,
            }
        )

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)

            # Check code uniqueness if changed
            if "code" in data and data["code"] != course.code:
                if Course.objects.filter(code=data["code"]).exists():
                    return JsonResponse(
                        {"error": "Course code already exists"}, status=400
                    )
                course.code = data["code"]

            course.title = data.get("title", course.title)
            course.credits = data.get("credits", course.credits)

            if "course_type" in data:
                course.course_type = data["course_type"]

            if "track" in data:
                course.track = data["track"]

            if "dept_id" in data:
                course.department_id = data["dept_id"] if data["dept_id"] else None

            if "category_id" in data:
                course.category_id = data["category_id"]

            if "is_active" in data:
                course.is_active = data["is_active"]

            course.save()

            return JsonResponse({"message": "Course updated successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        # Soft delete - just deactivate
        course.is_active = False
        course.save()
        return JsonResponse({"message": "Course deactivated successfully"})


# ============== UPDATED STUDENT API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def student_list(request):
    """List all students or create a new student"""
    if request.method == "GET":
        students = Student.objects.all().select_related("department")
        result = []
        for student in students:
            progress = calculate_progress(student)
            cgpa = calculate_cgpa(student)

            # Get minor courses count and credits
            minor_courses = StudentMinor.objects.filter(student=student).select_related(
                "course"
            )
            minor_count = minor_courses.count()
            minor_credits = sum(
                [m.course.credits for m in minor_courses if m.completed]
            )

            # Get elective courses count and credits
            elective_courses = StudentElective.objects.filter(
                student=student
            ).select_related("course")
            elective_count = elective_courses.count()
            elective_credits = sum(
                [e.course.credits for e in elective_courses if e.completed]
            )

            # Calculate major and required credits from completed_courses
            major_credits = 0
            required_credits = 0
            major_count = 0
            required_count = 0
            completed_courses_list = []

            for course_id, grade in student.completed_courses.items():
                # Don't skip IP or F grades - include them in the list
                try:
                    course = Course.objects.get(id=course_id)
                    if course.course_type == "major":
                        if grade not in ["IP", "F"]:
                            major_credits += course.credits
                            major_count += 1
                    elif course.course_type == "required":
                        if grade not in ["IP", "F"]:
                            required_credits += course.credits
                            required_count += 1

                    completed_courses_list.append(
                        {
                            "id": course_id,
                            "code": course.code,
                            "title": course.title,
                            "credits": course.credits,
                            "type": course.course_type,
                            "grade": grade,
                            "track": course.track,
                        }
                    )
                except Course.DoesNotExist:
                    continue

            # Get county display name
            county_display = ""
            if student.county:
                for code, name in LIBERIA_COUNTIES:
                    if code == student.county:
                        county_display = name
                        break

            result.append(
                {
                    "id": student.id,
                    "student_id": student.student_id,
                    "name": student.name,
                    "year": student.year,
                    "class_standing": get_class_standing(student),
                    "program_type": student.program_type,
                    "program_type_display": dict(Student.PROGRAM_TYPE_CHOICES).get(
                        student.program_type, "Major"
                    ),
                    "track": student.track,
                    "nationality": (
                        student.nationality.code if student.nationality else None
                    ),
                    "nationality_name": (
                        student.nationality.name if student.nationality else None
                    ),
                    "county": student.county,
                    "county_display": county_display,
                    "gender": student.gender,
                    "gender_display": dict(Student.GENDER_CHOICES).get(
                        student.gender, ""
                    ),
                    "religion": student.religion,
                    "religion_display": dict(Student.RELIGION_CHOICES).get(
                        student.religion, ""
                    ),
                    "date_of_birth": (
                        student.date_of_birth.strftime("%Y-%m-%d")
                        if student.date_of_birth
                        else None
                    ),
                    "department": (
                        student.department.name if student.department else None
                    ),
                    "department_id": student.department_id,
                    "department_code": (
                        student.department.code if student.department else None
                    ),
                    "completed": {
                        "required": required_count,
                        "major": major_count,
                        "minor": minor_count,
                        "electives": elective_count,
                        "required_credits": required_credits,
                        "major_credits": major_credits,
                        "minor_credits": minor_credits,
                        "elective_credits": elective_credits,
                        "total_credits": required_credits
                        + major_credits
                        + minor_credits
                        + elective_credits,
                        "courses": completed_courses_list,
                    },
                    "progress": progress,
                    "cgpa": round(cgpa, 2),
                    "progress_percent": progress["percent_complete"],
                    "minor_count": minor_count,
                    "elective_count": elective_count,
                    "status": student.status,
                    "photo_url": (
                        student.photo.url
                        if student.photo
                        else (student.photo_url if student.photo_url else None)
                    ),
                    "email": student.email,
                    "phone": student.phone,
                    "enrollment_date": (
                        student.enrollment_date.strftime("%Y-%m-%d")
                        if student.enrollment_date
                        else None
                    ),
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            if Student.objects.filter(student_id=data["student_id"]).exists():
                return JsonResponse({"error": "Student ID already exists"}, status=400)

            # Create student with new fields
            student = Student.objects.create(
                student_id=data["student_id"],
                name=data["name"],
                year=data["year"],
                program_type=data.get("program_type", "major"),
                track=data.get("track"),
                nationality=data.get("nationality"),
                county=data.get("county"),
                gender=data.get("gender"),
                religion=data.get("religion"),
                date_of_birth=data.get("date_of_birth"),
                department_id=data.get("department_id"),
                completed_courses={},  # Always start with empty completed courses
                status="active",
                email=data.get("email", ""),
                phone=data.get("phone", ""),
                photo_url=data.get("photo_url", ""),
                enrollment_date=timezone.now().date(),
            )

            return JsonResponse(
                {"id": student.id, "message": "Student created successfully"}
            )
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def student_detail(request, pk):
    """Get, update, or delete a specific student"""
    try:
        student = Student.objects.get(pk=pk)
    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)

    if request.method == "GET":
        progress = calculate_progress(student)
        cgpa = calculate_cgpa(student)

        # Get county display name
        county_display = ""
        if student.county:
            for code, name in LIBERIA_COUNTIES:
                if code == student.county:
                    county_display = name
                    break

        return JsonResponse(
            {
                "id": student.id,
                "student_id": student.student_id,
                "name": student.name,
                "year": student.year,
                "program_type": student.program_type,
                "track": student.track,
                "nationality": (
                    student.nationality.code if student.nationality else None
                ),
                "nationality_name": (
                    student.nationality.name if student.nationality else None
                ),
                "county": student.county,
                "county_display": county_display,
                "gender": student.gender,
                "religion": student.religion,
                "date_of_birth": (
                    student.date_of_birth.strftime("%Y-%m-%d")
                    if student.date_of_birth
                    else None
                ),
                "department_id": student.department_id,
                "completed": student.completed_courses,
                "progress": progress,
                "cgpa": round(cgpa, 2),
                "status": student.status,
                "photo_url": (
                    student.photo.url
                    if student.photo
                    else (student.photo_url if student.photo_url else None)
                ),
                "email": student.email,
                "phone": student.phone,
            }
        )

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            student.student_id = data.get("student_id", student.student_id)
            student.name = data.get("name", student.name)
            student.year = data.get("year", student.year)
            student.program_type = data.get("program_type", student.program_type)
            student.track = data.get("track", student.track)
            student.nationality = data.get("nationality", student.nationality)
            student.county = data.get("county", student.county)
            student.gender = data.get("gender", student.gender)
            student.religion = data.get("religion", student.religion)
            student.date_of_birth = data.get("date_of_birth", student.date_of_birth)
            student.department_id = data.get("department_id", student.department_id)

            # CRITICAL FIX: Merge completed courses instead of replacing
            if "completed" in data:
                # Get existing completed courses
                existing_completed = student.completed_courses
                # Update with new grades (preserving existing ones)
                existing_completed.update(data["completed"])
                student.completed_courses = existing_completed

            student.status = data.get("status", student.status)
            student.email = data.get("email", student.email)
            student.phone = data.get("phone", student.phone)
            if data.get("photo_url"):
                student.photo_url = data.get("photo_url")
            student.save()

            return JsonResponse({"message": "Student updated successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        student.status = "deleted"
        student.save()
        return JsonResponse({"message": "Student deleted successfully"})


# ============== UPDATED TEACHER API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def teacher_list(request):
    """List all teachers or create a new teacher"""
    if request.method == "GET":
        teachers = Teacher.objects.filter(is_active=True).select_related("department")
        result = []
        for teacher in teachers:
            # Get assignment count
            assignment_count = TeacherAssignment.objects.filter(teacher=teacher).count()

            # Get county display name
            county_display = ""
            if teacher.county:
                for code, name in LIBERIA_COUNTIES:
                    if code == teacher.county:
                        county_display = name
                        break

            result.append(
                {
                    "id": teacher.id,
                    "teacher_id": teacher.teacher_id,
                    "name": teacher.name,
                    "dept": teacher.department.name if teacher.department else None,
                    "dept_id": teacher.department_id,
                    "dept_code": (
                        teacher.department.code if teacher.department else None
                    ),
                    "email": teacher.email,
                    "phone": teacher.phone,
                    "nationality": (
                        teacher.nationality.code if teacher.nationality else None
                    ),
                    "nationality_name": (
                        teacher.nationality.name if teacher.nationality else None
                    ),
                    "county": teacher.county,
                    "county_display": county_display,
                    "gender": teacher.gender,
                    "gender_display": dict(Teacher.GENDER_CHOICES).get(
                        teacher.gender, ""
                    ),
                    "religion": teacher.religion,
                    "religion_display": dict(Teacher.RELIGION_CHOICES).get(
                        teacher.religion, ""
                    ),
                    "date_of_birth": (
                        teacher.date_of_birth.strftime("%Y-%m-%d")
                        if teacher.date_of_birth
                        else None
                    ),
                    "assignment_count": assignment_count,
                    "photo_url": (
                        teacher.photo.url
                        if teacher.photo
                        else (teacher.photo_url if teacher.photo_url else None)
                    ),
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            if Teacher.objects.filter(teacher_id=data["teacher_id"]).exists():
                return JsonResponse({"error": "Teacher ID already exists"}, status=400)

            if Teacher.objects.filter(email=data["email"]).exists():
                return JsonResponse({"error": "Email already exists"}, status=400)

            department = Department.objects.get(id=data["dept_id"])

            teacher = Teacher.objects.create(
                teacher_id=data["teacher_id"],
                name=data["name"],
                department=department,
                email=data["email"],
                phone=data.get("phone", ""),
                nationality=data.get("nationality"),
                county=data.get("county"),
                gender=data.get("gender"),
                religion=data.get("religion"),
                date_of_birth=data.get("date_of_birth"),
            )

            return JsonResponse(
                {"id": teacher.id, "message": "Teacher created successfully"}
            )
        except Department.DoesNotExist:
            return JsonResponse({"error": "Department not found"}, status=404)
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def teacher_detail(request, pk):
    """Get, update, or delete a specific teacher"""
    try:
        teacher = Teacher.objects.get(pk=pk)
    except Teacher.DoesNotExist:
        return JsonResponse({"error": "Teacher not found"}, status=404)

    if request.method == "GET":
        # Get county display name
        county_display = ""
        if teacher.county:
            for code, name in LIBERIA_COUNTIES:
                if code == teacher.county:
                    county_display = name
                    break

        return JsonResponse(
            {
                "id": teacher.id,
                "teacher_id": teacher.teacher_id,
                "name": teacher.name,
                "dept_id": teacher.department_id,
                "dept": teacher.department.name if teacher.department else None,
                "email": teacher.email,
                "phone": teacher.phone,
                "nationality": (
                    teacher.nationality.code if teacher.nationality else None
                ),
                "nationality_name": (
                    teacher.nationality.name if teacher.nationality else None
                ),
                "county": teacher.county,
                "county_display": county_display,
                "gender": teacher.gender,
                "religion": teacher.religion,
                "date_of_birth": (
                    teacher.date_of_birth.strftime("%Y-%m-%d")
                    if teacher.date_of_birth
                    else None
                ),
                "photo_url": (
                    teacher.photo.url
                    if teacher.photo
                    else (teacher.photo_url if teacher.photo_url else None)
                ),
            }
        )

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            teacher.teacher_id = data.get("teacher_id", teacher.teacher_id)
            teacher.name = data.get("name", teacher.name)

            if "dept_id" in data:
                teacher.department = Department.objects.get(id=data["dept_id"])

            teacher.email = data.get("email", teacher.email)
            teacher.phone = data.get("phone", teacher.phone)
            teacher.nationality = data.get("nationality", teacher.nationality)
            teacher.county = data.get("county", teacher.county)
            teacher.gender = data.get("gender", teacher.gender)
            teacher.religion = data.get("religion", teacher.religion)
            teacher.date_of_birth = data.get("date_of_birth", teacher.date_of_birth)

            if data.get("photo_url"):
                teacher.photo_url = data.get("photo_url")
            teacher.save()

            return JsonResponse({"message": "Teacher updated successfully"})
        except Department.DoesNotExist:
            return JsonResponse({"error": "Department not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        teacher.is_active = False
        teacher.save()
        return JsonResponse({"message": "Teacher deleted successfully"})


# ============== TEACHER ASSIGNMENT API ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def assignment_list(request):
    """List all teacher assignments or create/update assignment"""
    if request.method == "GET":
        assignments = TeacherAssignment.objects.all().select_related("teacher")
        result = []
        for assignment in assignments:
            courses_list = []
            for course in assignment.courses.all():
                courses_list.append(
                    {
                        "id": course.id,
                        "code": course.code,
                        "title": course.title,
                        "credits": course.credits,
                    }
                )

            result.append(
                {
                    "teacherId": assignment.teacher_id,
                    "teacherName": assignment.teacher.name,
                    "courseIds": list(assignment.courses.values_list("id", flat=True)),
                    "courses": courses_list,
                    "semester": assignment.semester,
                    "year": assignment.year,
                }
            )
        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            teacher = Teacher.objects.get(id=data["teacherId"])

            # Get or create assignment
            assignment, created = TeacherAssignment.objects.get_or_create(
                teacher=teacher,
                defaults={
                    "semester": data.get("semester", "semester1"),
                    "year": data.get("year", timezone.now().year),
                },
            )

            # Update courses
            if "courseIds" in data:
                courses = Course.objects.filter(id__in=data["courseIds"])
                assignment.courses.set(courses)

            return JsonResponse({"message": "Assignment saved successfully"})
        except Teacher.DoesNotExist:
            return JsonResponse({"error": "Teacher not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
@csrf_exempt
def assignment_detail(request, teacher_id):
    """Delete a specific teacher assignment"""
    try:
        assignment = TeacherAssignment.objects.get(teacher_id=teacher_id)
    except TeacherAssignment.DoesNotExist:
        return JsonResponse({"error": "Assignment not found"}, status=404)

    if request.method == "DELETE":
        assignment.delete()
        return JsonResponse({"message": "Assignment deleted successfully"})


# ============== ENHANCED GRADE ENTRY API WITH SEMESTER 1/2 ==============
@login_required
@require_http_methods(["POST"])
@csrf_exempt
def grade_entry(request):
    """Record a grade for a student in a course with semester tracking"""
    try:
        data = json.loads(request.body)
        student = Student.objects.get(id=data["studentId"])
        course_id = data["courseId"]
        grade = data["grade"]
        semester = data.get("semester", "semester1")  # semester1 or semester2
        year = data.get("year", timezone.now().year)
        date_recorded = data.get("date_recorded", timezone.now().date().isoformat())

        # Validate grade
        valid_grades = ["A", "A-", "B+", "B", "B-", "C+", "C", "D", "F", "IP"]
        if grade not in valid_grades:
            return JsonResponse({"error": "Invalid grade"}, status=400)

        # Validate semester
        valid_semesters = ["semester1", "semester2"]
        if semester not in valid_semesters:
            return JsonResponse(
                {"error": "Invalid semester. Must be semester1 or semester2"},
                status=400,
            )

        # Update completed courses - MERGE with existing
        completed = student.completed_courses
        completed[course_id] = grade
        student.completed_courses = completed
        student.save()

        # Get course to determine type
        try:
            course = Course.objects.get(id=course_id)

            # Create or update GradeRecord
            grade_record, created = GradeRecord.objects.update_or_create(
                student=student,
                course=course,
                semester=semester,
                year=year,
                defaults={
                    "grade": grade,
                    "date_recorded": date_recorded,
                    "is_completed": grade not in ["IP", None],
                },
            )

            # If it's a minor course, update StudentMinor record
            if course.course_type == "minor":
                StudentMinor.objects.update_or_create(
                    student=student,
                    course=course,
                    defaults={
                        "grade": grade,
                        "completed": grade not in ["IP", None],
                        "semester": semester,
                        "year": year,
                    },
                )
            # If it's an elective course, update StudentElective record
            elif course.course_type == "elective":
                StudentElective.objects.update_or_create(
                    student=student,
                    course=course,
                    defaults={
                        "grade": grade,
                        "completed": grade not in ["IP", None],
                        "semester": semester,
                        "year": year,
                    },
                )
        except Course.DoesNotExist:
            pass

        return JsonResponse(
            {
                "message": f"Grade {grade} recorded successfully",
                "semester": semester,
                "year": year,
                "date": date_recorded,
            }
        )
    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)
    except KeyError as e:
        return JsonResponse({"error": f"Missing field: {e}"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== BULK GRADE ENTRY ==============
@login_required
@require_http_methods(["POST"])
@csrf_exempt
def bulk_grade_entry(request):
    """Submit multiple grades at once"""
    try:
        data = json.loads(request.body)
        grades = data.get("grades", [])
        semester = data.get("semester", "semester1")
        year = data.get("year", timezone.now().year)
        date_recorded = data.get("date_recorded", timezone.now().date().isoformat())

        for grade_entry in grades:
            student = Student.objects.get(id=grade_entry["studentId"])
            course_id = grade_entry["courseId"]
            grade = grade_entry["grade"]

            # Merge with existing grades
            completed = student.completed_courses
            completed[course_id] = grade
            student.completed_courses = completed
            student.save()

            # Create GradeRecord
            try:
                course = Course.objects.get(id=course_id)
                GradeRecord.objects.update_or_create(
                    student=student,
                    course=course,
                    semester=semester,
                    year=year,
                    defaults={
                        "grade": grade,
                        "date_recorded": date_recorded,
                        "is_completed": grade not in ["IP", None],
                    },
                )
            except Course.DoesNotExist:
                continue

        return JsonResponse(
            {
                "message": f"{len(grades)} grades recorded successfully",
                "semester": semester,
                "year": year,
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== GET GRADE RECORDS WITH FILTERS ==============
@login_required
@require_http_methods(["GET"])
def get_grade_records(request):
    """Get grade records with semester/year filters"""
    try:
        semester = request.GET.get("semester")
        year = request.GET.get("year")
        student_id = request.GET.get("student_id")
        course_id = request.GET.get("course_id")

        grades = GradeRecord.objects.all().select_related("student", "course")

        if semester:
            grades = grades.filter(semester=semester)
        if year:
            grades = grades.filter(year=year)
        if student_id:
            grades = grades.filter(student_id=student_id)
        if course_id:
            grades = grades.filter(course_id=course_id)

        grades = grades.order_by("-year", "-semester", "-date_recorded")

        result = []
        for grade in grades:
            result.append(
                {
                    "id": grade.id,
                    "student_id": grade.student.student_id,
                    "student_name": grade.student.name,
                    "course_code": grade.course.code,
                    "course_title": grade.course.title,
                    "grade": grade.grade,
                    "semester": grade.semester,
                    "year": grade.year,
                    "date_recorded": (
                        grade.date_recorded.strftime("%Y-%m-%d")
                        if grade.date_recorded
                        else None
                    ),
                    "is_completed": grade.is_completed,
                }
            )

        return JsonResponse(result, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== GET SEMESTER STATISTICS ==============
@login_required
@require_http_methods(["GET"])
def get_semester_stats(request):
    """Get statistics grouped by semester and year"""
    try:
        # Get all distinct semester-year combinations with grade counts
        stats = (
            GradeRecord.objects.values("semester", "year")
            .annotate(
                total_grades=Count("id"),
                completed_grades=Count("id", filter=Q(is_completed=True)),
            )
            .order_by("-year", "-semester")
        )

        result = []
        for stat in stats:
            semester_display = (
                "Semester 1" if stat["semester"] == "semester1" else "Semester 2"
            )
            result.append(
                {
                    "semester": stat["semester"],
                    "semester_display": semester_display,
                    "year": stat["year"],
                    "total_grades": stat["total_grades"],
                    "completed_grades": stat["completed_grades"],
                    "display": f"{semester_display} {stat['year']}",
                }
            )

        return JsonResponse(result, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== FIXED LIBRARY API - RETURNS ARRAY ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def library_list(request):
    """List all library books with track information or add a new book"""
    if request.method == "GET":
        books = LibraryBook.objects.all().select_related("category", "uploaded_by")

        # Apply filters
        track = request.GET.get("track")
        category_id = request.GET.get("category")
        search = request.GET.get("search")

        if track:
            books = books.filter(track=track)
        if category_id:
            books = books.filter(category_id=category_id)
        if search:
            books = books.filter(
                Q(title__icontains=search)
                | Q(author__icontains=search)
                | Q(description__icontains=search)
            )

        books = books.order_by("-uploaded_at")

        # Return simple array for frontend compatibility
        result = []
        for book in books:
            result.append(
                {
                    "id": book.id,
                    "title": book.title,
                    "author": book.author,
                    "category_id": book.category_id,
                    "category_name": book.category.name if book.category else None,
                    "track": book.track,
                    "track_display": dict(LibraryBook.TRACK_CHOICES).get(
                        book.track, "All Tracks"
                    ),
                    "description": book.description,
                    "pdf_url": book.pdf_file.url if book.pdf_file else book.pdf_url,
                    "pdf_file": book.pdf_file.name if book.pdf_file else None,
                    "cover_color": book.cover_color,
                    "cover_image": book.cover_image.url if book.cover_image else None,
                    "uploaded_by": book.uploaded_by.name if book.uploaded_by else None,
                    "uploaded_at": book.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                    "download_count": book.download_count,
                    "view_count": book.view_count,
                }
            )

        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            # Validate track
            valid_tracks = ["ALL", "IR", "CP", "LGP"]
            track = data.get("track", "ALL")
            if track not in valid_tracks:
                return JsonResponse({"error": "Invalid track selection"}, status=400)

            book = LibraryBook.objects.create(
                title=data["title"],
                author=data["author"],
                category_id=data.get("category_id"),
                track=track,
                description=data.get("description", ""),
                pdf_url=data.get("pdf_url", ""),
                cover_color=data.get("cover_color", "bg-blue-900"),
                uploaded_by_id=(
                    request.user.teacher.id
                    if hasattr(request.user, "teacher")
                    else None
                ),
            )

            return JsonResponse(
                {
                    "id": book.id,
                    "message": "Book added successfully",
                    "track": book.track,
                }
            )
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


# ============== LIBRARY DETAIL (GET, PUT, DELETE) ==============
@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def library_detail(request, pk):
    """Get, update, or delete a specific library book"""
    try:
        book = LibraryBook.objects.get(pk=pk)
    except LibraryBook.DoesNotExist:
        return JsonResponse({"error": "Book not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "category_id": book.category_id,
                "category_name": book.category.name if book.category else None,
                "track": book.track,
                "track_display": dict(LibraryBook.TRACK_CHOICES).get(
                    book.track, "All Tracks"
                ),
                "description": book.description,
                "pdf_url": book.pdf_file.url if book.pdf_file else book.pdf_url,
                "cover_color": book.cover_color,
                "cover_image": book.cover_image.url if book.cover_image else None,
                "uploaded_at": book.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                "download_count": book.download_count,
                "view_count": book.view_count,
            }
        )

    elif request.method == "PUT":
        try:
            # Handle both JSON and multipart form data
            if request.content_type and "multipart/form-data" in request.content_type:
                # Handle form data
                book.title = request.POST.get("title", book.title)
                book.author = request.POST.get("author", book.author)
                book.category_id = request.POST.get("category_id", book.category_id)
                book.track = request.POST.get("track", book.track)
                book.description = request.POST.get("description", book.description)
                book.cover_color = request.POST.get("cover_color", book.cover_color)

                # Handle PDF file if provided
                if request.FILES.get("pdf"):
                    # Delete old file
                    if book.pdf_file:
                        try:
                            os.remove(book.pdf_file.path)
                        except:
                            pass

                    # Save new file
                    pdf_file = request.FILES["pdf"]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{book.title.replace(' ', '_')}_{timestamp}.pdf"
                    filename = filename.replace("/", "_").replace("\\", "_")

                    library_dir = os.path.join(settings.MEDIA_ROOT, "library")
                    os.makedirs(library_dir, exist_ok=True)

                    fs = FileSystemStorage(location=library_dir)
                    filename = fs.save(filename, pdf_file)
                    book.pdf_file = f"library/{filename}"

                # Handle cover image if provided
                if request.FILES.get("cover_image"):
                    if book.cover_image:
                        try:
                            os.remove(book.cover_image.path)
                        except:
                            pass

                    cover_image = request.FILES["cover_image"]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"cover_{book.title.replace(' ', '_')}_{timestamp}.{cover_image.name.split('.')[-1]}"

                    fs = FileSystemStorage(location=library_dir)
                    filename = fs.save(filename, cover_image)
                    book.cover_image = f"library/{filename}"
            else:
                # Handle JSON data
                data = json.loads(request.body)
                book.title = data.get("title", book.title)
                book.author = data.get("author", book.author)
                book.category_id = data.get("category_id", book.category_id)
                book.track = data.get("track", book.track)
                book.description = data.get("description", book.description)
                book.cover_color = data.get("cover_color", book.cover_color)

            book.save()
            return JsonResponse({"message": "Book updated successfully", "id": book.id})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        # Delete associated files
        if book.pdf_file:
            try:
                os.remove(book.pdf_file.path)
            except:
                pass
        if book.cover_image:
            try:
                os.remove(book.cover_image.path)
            except:
                pass
        book.delete()
        return JsonResponse({"message": "Book deleted successfully"})


# ============== FIXED DOCUMENT API - RETURNS ARRAY ==============
@login_required
@require_http_methods(["GET", "POST"])
@csrf_exempt
def document_list(request):
    """List all documents or add a new document"""
    if request.method == "GET":
        documents = DepartmentDocument.objects.all().select_related("uploaded_by")

        # Apply filters
        track = request.GET.get("track")
        document_type = request.GET.get("type")
        category = request.GET.get("category")
        search = request.GET.get("search")

        if track:
            documents = documents.filter(track=track)
        if document_type:
            documents = documents.filter(document_type=document_type)
        if category:
            documents = documents.filter(category__icontains=category)
        if search:
            documents = documents.filter(
                Q(title__icontains=search)
                | Q(author__icontains=search)
                | Q(description__icontains=search)
                | Q(category__icontains=search)
            )

        documents = documents.order_by("-uploaded_at")

        # Return simple array for frontend compatibility
        result = []
        for doc in documents:
            file_icon = {
                "pdf": "fa-file-pdf",
                "word": "fa-file-word",
                "image": "fa-file-image",
            }.get(doc.document_type, "fa-file")

            result.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "author": doc.author,
                    "document_type": doc.document_type,
                    "track": doc.track,
                    "track_display": dict(DepartmentDocument.TRACK_CHOICES).get(
                        doc.track, "All Tracks"
                    ),
                    "file_url": doc.file.url if doc.file else None,
                    "file_name": doc.file.name if doc.file else None,
                    "file_size": doc.file_size,
                    "description": doc.description,
                    "category": doc.category,
                    "uploaded_by": doc.uploaded_by.name if doc.uploaded_by else None,
                    "uploaded_by_id": doc.uploaded_by_id,
                    "uploaded_at": doc.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                    "file_icon": file_icon,
                    "download_count": doc.download_count,
                }
            )

        return JsonResponse(result, safe=False)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)

            # Validate track
            valid_tracks = ["ALL", "IR", "CP", "LGP"]
            track = data.get("track", "ALL")
            if track not in valid_tracks:
                return JsonResponse({"error": "Invalid track selection"}, status=400)

            document = DepartmentDocument.objects.create(
                title=data["title"],
                author=data["author"],
                document_type=data["document_type"],
                track=track,
                file_url=data.get("file_url", ""),
                description=data.get("description", ""),
                category=data.get("category", ""),
                uploaded_by_id=data.get("uploaded_by_id"),
            )

            return JsonResponse(
                {
                    "id": document.id,
                    "message": "Document added successfully",
                    "track": track,
                }
            )
        except KeyError as e:
            return JsonResponse({"error": f"Missing field: {e}"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


# ============== DOCUMENT DETAIL (GET, PUT, DELETE) ==============
@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
@csrf_exempt
def document_detail(request, pk):
    """Get, update, or delete a specific document"""
    try:
        document = DepartmentDocument.objects.get(pk=pk)
    except DepartmentDocument.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(
            {
                "id": document.id,
                "title": document.title,
                "author": document.author,
                "document_type": document.document_type,
                "track": document.track,
                "track_display": dict(DepartmentDocument.TRACK_CHOICES).get(
                    document.track, "All Tracks"
                ),
                "file_url": document.file.url if document.file else None,
                "file_name": document.file.name if document.file else None,
                "file_size": document.file_size,
                "description": document.description,
                "category": document.category,
                "uploaded_by": (
                    document.uploaded_by.name if document.uploaded_by else None
                ),
                "uploaded_by_id": document.uploaded_by_id,
                "uploaded_at": document.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                "download_count": document.download_count,
            }
        )

    elif request.method == "PUT":
        try:
            # Handle both JSON and multipart form data
            if request.content_type and "multipart/form-data" in request.content_type:
                # Handle form data
                document.title = request.POST.get("title", document.title)
                document.author = request.POST.get("author", document.author)
                document.document_type = request.POST.get(
                    "document_type", document.document_type
                )
                document.track = request.POST.get("track", document.track)
                document.description = request.POST.get(
                    "description", document.description
                )
                document.category = request.POST.get("category", document.category)

                # Handle file if provided
                if request.FILES.get("document"):
                    # Delete old file
                    if document.file:
                        try:
                            os.remove(document.file.path)
                        except:
                            pass

                    # Save new file
                    doc_file = request.FILES["document"]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_extension = doc_file.name.split(".")[-1].lower()
                    filename = f"{document.title.replace(' ', '_')}_{timestamp}.{file_extension}"
                    filename = filename.replace("/", "_").replace("\\", "_")

                    docs_dir = os.path.join(settings.MEDIA_ROOT, "documents")
                    os.makedirs(docs_dir, exist_ok=True)

                    fs = FileSystemStorage(location=docs_dir)
                    filename = fs.save(filename, doc_file)
                    document.file = f"documents/{filename}"

                    # Update file size
                    file_size_bytes = doc_file.size
                    if file_size_bytes < 1024:
                        document.file_size = f"{file_size_bytes} B"
                    elif file_size_bytes < 1024 * 1024:
                        document.file_size = f"{file_size_bytes / 1024:.1f} KB"
                    else:
                        document.file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"
            else:
                # Handle JSON data
                data = json.loads(request.body)
                document.title = data.get("title", document.title)
                document.author = data.get("author", document.author)
                document.document_type = data.get(
                    "document_type", document.document_type
                )
                document.track = data.get("track", document.track)
                document.description = data.get("description", document.description)
                document.category = data.get("category", document.category)

            document.save()
            return JsonResponse(
                {"message": "Document updated successfully", "id": document.id}
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    elif request.method == "DELETE":
        # Delete file if exists
        if document.file:
            try:
                os.remove(document.file.path)
            except:
                pass
        document.delete()
        return JsonResponse({"message": "Document deleted successfully"})


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def upload_pdf(request):
    """Handle PDF file upload for library"""
    try:
        title = request.POST.get("title")
        author = request.POST.get("author")
        category_id = request.POST.get("category_id")
        track = request.POST.get("track", "ALL")
        description = request.POST.get("description", "")
        pdf_file = request.FILES.get("pdf")
        cover_image = request.FILES.get("cover_image")

        if not pdf_file:
            return JsonResponse({"error": "No PDF file provided"}, status=400)

        if not pdf_file.name.endswith(".pdf"):
            return JsonResponse({"error": "File must be a PDF"}, status=400)

        # Validate track
        valid_tracks = ["ALL", "IR", "CP", "LGP"]
        if track not in valid_tracks:
            return JsonResponse({"error": "Invalid track selection"}, status=400)

        # Create library directory if it doesn't exist
        library_dir = os.path.join(settings.MEDIA_ROOT, "library")
        os.makedirs(library_dir, exist_ok=True)

        # Generate unique filename for PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{title.replace(' ', '_')}_{timestamp}.pdf"
        pdf_filename = pdf_filename.replace("/", "_").replace("\\", "_")

        # Save PDF file
        fs = FileSystemStorage(location=library_dir)
        pdf_filename = fs.save(pdf_filename, pdf_file)
        pdf_url = f"{settings.MEDIA_URL}library/{pdf_filename}"

        # Handle cover image if provided
        cover_filename = None
        if cover_image:
            cover_filename = f"cover_{title.replace(' ', '_')}_{timestamp}.{cover_image.name.split('.')[-1]}"
            cover_filename = fs.save(cover_filename, cover_image)
            cover_url = f"{settings.MEDIA_URL}library/{cover_filename}"

        # Create library book
        book = LibraryBook.objects.create(
            title=title,
            author=author,
            category_id=category_id,
            track=track,
            description=description,
            pdf_file=f"library/{pdf_filename}",
            cover_image=f"library/{cover_filename}" if cover_filename else None,
            uploaded_by_id=(
                request.user.teacher.id if hasattr(request.user, "teacher") else None
            ),
        )

        return JsonResponse(
            {
                "id": book.id,
                "message": "PDF uploaded successfully",
                "pdf_url": pdf_url,
                "track": track,
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def upload_document_file(request):
    """Handle document file upload with custom category"""
    try:
        title = request.POST.get("title")
        author = request.POST.get("author")
        document_type = request.POST.get("document_type")
        track = request.POST.get("track", "ALL")
        category = request.POST.get("category", "")
        description = request.POST.get("description", "")
        document_file = request.FILES.get("document")

        if not document_file:
            return JsonResponse({"error": "No file provided"}, status=400)

        # Validate file type
        file_extension = document_file.name.split(".")[-1].lower()

        if document_type == "pdf" and file_extension != "pdf":
            return JsonResponse({"error": "File must be a PDF"}, status=400)
        elif document_type == "word" and file_extension not in ["doc", "docx"]:
            return JsonResponse({"error": "File must be a Word document"}, status=400)
        elif document_type == "image" and file_extension not in [
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
        ]:
            return JsonResponse({"error": "File must be an image"}, status=400)

        # Validate track
        valid_tracks = ["ALL", "IR", "CP", "LGP"]
        if track not in valid_tracks:
            return JsonResponse({"error": "Invalid track selection"}, status=400)

        # Create documents directory if it doesn't exist
        docs_dir = os.path.join(settings.MEDIA_ROOT, "documents")
        os.makedirs(docs_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{title.replace(' ', '_')}_{timestamp}.{file_extension}"
        filename = filename.replace("/", "_").replace("\\", "_")

        # Save file
        fs = FileSystemStorage(location=docs_dir)
        filename = fs.save(filename, document_file)
        file_url = f"{settings.MEDIA_URL}documents/{filename}"

        # Get file size
        file_size_bytes = document_file.size
        if file_size_bytes < 1024:
            file_size = f"{file_size_bytes} B"
        elif file_size_bytes < 1024 * 1024:
            file_size = f"{file_size_bytes / 1024:.1f} KB"
        else:
            file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"

        # Create document record
        document = DepartmentDocument.objects.create(
            title=title,
            author=author,
            document_type=document_type,
            track=track,
            file=f"documents/{filename}",
            file_size=file_size,
            description=description,
            category=category,
            uploaded_by_id=(
                request.user.teacher.id if hasattr(request.user, "teacher") else None
            ),
        )

        return JsonResponse(
            {
                "id": document.id,
                "message": "Document uploaded successfully",
                "file_url": file_url,
                "file_size": file_size,
                "track": track,
                "category": category,
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== ENHANCED ANALYTICS WITH DEMOGRAPHICS ==============
@login_required
@require_http_methods(["GET"])
def get_enhanced_analytics(request):
    """Get comprehensive analytics data including demographics"""
    students = Student.objects.all()
    teachers = Teacher.objects.filter(is_active=True)
    courses = Course.objects.all()
    grade_records = GradeRecord.objects.all()

    # Student distribution by program type (major/minor)
    program_distribution = {
        "major": students.filter(program_type="major").count(),
        "minor": students.filter(program_type="minor").count(),
    }

    # Student distribution by gender
    student_gender_distribution = {
        "male": students.filter(gender="M").count(),
        "female": students.filter(gender="F").count(),
        "other": students.filter(gender="O").count(),
        "unspecified": students.filter(gender__isnull=True).count(),
    }

    # Teacher distribution by gender
    teacher_gender_distribution = {
        "male": teachers.filter(gender="M").count(),
        "female": teachers.filter(gender="F").count(),
        "other": teachers.filter(gender="O").count(),
        "unspecified": teachers.filter(gender__isnull=True).count(),
    }

    # Student distribution by nationality
    student_nationalities = {}
    for student in students.exclude(nationality__isnull=True):
        country_code = student.nationality.code
        student_nationalities[country_code] = (
            student_nationalities.get(country_code, 0) + 1
        )

    # Teacher distribution by nationality
    teacher_nationalities = {}
    for teacher in teachers.exclude(nationality__isnull=True):
        country_code = teacher.nationality.code
        teacher_nationalities[country_code] = (
            teacher_nationalities.get(country_code, 0) + 1
        )

    # Student distribution by county (Liberia)
    student_counties = {}
    for student in students.exclude(county__isnull=True).exclude(county=""):
        county_display = ""
        for code, name in LIBERIA_COUNTIES:
            if code == student.county:
                county_display = name
                break
        if county_display:
            student_counties[county_display] = (
                student_counties.get(county_display, 0) + 1
            )

    # Teacher distribution by county
    teacher_counties = {}
    for teacher in teachers.exclude(county__isnull=True).exclude(county=""):
        county_display = ""
        for code, name in LIBERIA_COUNTIES:
            if code == teacher.county:
                county_display = name
                break
        if county_display:
            teacher_counties[county_display] = (
                teacher_counties.get(county_display, 0) + 1
            )

    # Student distribution by religion
    student_religion_distribution = {
        "Christianity": students.filter(religion="Christianity").count(),
        "Islam": students.filter(religion="Islam").count(),
        "Traditional": students.filter(religion="Traditional").count(),
        "Other": students.filter(religion="Other").count(),
        "None": students.filter(religion="None").count(),
        "Unspecified": students.filter(religion__isnull=True).count(),
    }

    # Teacher distribution by religion
    teacher_religion_distribution = {
        "Christianity": teachers.filter(religion="Christianity").count(),
        "Islam": teachers.filter(religion="Islam").count(),
        "Traditional": teachers.filter(religion="Traditional").count(),
        "Other": teachers.filter(religion="Other").count(),
        "None": teachers.filter(religion="None").count(),
        "Unspecified": teachers.filter(religion__isnull=True).count(),
    }

    # Grade distribution
    grade_distribution = {
        "A": 0,
        "A-": 0,
        "B+": 0,
        "B": 0,
        "B-": 0,
        "C+": 0,
        "C": 0,
        "D": 0,
        "F": 0,
        "IP": 0,
    }
    for grade in grade_records:
        if grade.grade in grade_distribution:
            grade_distribution[grade.grade] += 1

    # Course distribution by type
    course_distribution = {
        "major": courses.filter(course_type="major").count(),
        "minor": courses.filter(course_type="minor").count(),
        "elective": courses.filter(course_type="elective").count(),
        "required": courses.filter(course_type="required").count(),
    }

    # Graduation rates by year
    graduation_rates = {}
    for year in range(2020, 2026):
        year_students = students.filter(year=year)
        total = year_students.count()
        if total > 0:
            grads = year_students.filter(status="graduated").count()
            graduation_rates[f"Class of {year}"] = round((grads / total) * 100, 1)

    data = {
        "program_distribution": program_distribution,
        "student_gender_distribution": student_gender_distribution,
        "teacher_gender_distribution": teacher_gender_distribution,
        "student_nationalities": student_nationalities,
        "teacher_nationalities": teacher_nationalities,
        "student_counties": student_counties,
        "teacher_counties": teacher_counties,
        "student_religion_distribution": student_religion_distribution,
        "teacher_religion_distribution": teacher_religion_distribution,
        "grade_distribution": grade_distribution,
        "course_distribution": course_distribution,
        "graduation_rates": graduation_rates,
    }

    return JsonResponse(data)


# ============== GET ANALYTICS (ORIGINAL) ==============
@login_required
@require_http_methods(["GET"])
def get_analytics(request):
    """Get comprehensive analytics data (original version)"""
    students = Student.objects.all()
    courses = Course.objects.all()
    documents = DepartmentDocument.objects.all()
    grade_records = GradeRecord.objects.all()

    # Student distribution by track
    student_distribution = {
        "IR": students.filter(track="IR").count(),
        "CP": students.filter(track="CP").count(),
        "LGP": students.filter(track="LGP").count(),
    }

    # Grade distribution
    grade_distribution = {
        "A": 0,
        "A-": 0,
        "B+": 0,
        "B": 0,
        "B-": 0,
        "C+": 0,
        "C": 0,
        "D": 0,
        "F": 0,
    }
    for grade in grade_records:
        if grade.grade in grade_distribution:
            grade_distribution[grade.grade] += 1

    # Course distribution by type
    course_distribution = {
        "major": courses.filter(course_type="major").count(),
        "minor": courses.filter(course_type="minor").count(),
        "elective": courses.filter(course_type="elective").count(),
        "required": courses.filter(course_type="required").count(),
    }

    # Graduation rates by year
    graduation_rates = {}
    for year in [2022, 2023, 2024, 2025]:
        year_students = students.filter(year=year)
        total = year_students.count()
        if total > 0:
            grads = year_students.filter(status="graduated").count()
            graduation_rates[f"Class of {year}"] = round((grads / total) * 100, 1)

    # Document statistics by track
    document_stats = {
        "total": documents.count(),
        "pdf": documents.filter(document_type="pdf").count(),
        "word": documents.filter(document_type="word").count(),
        "image": documents.filter(document_type="image").count(),
        "by_track": {
            "IR": documents.filter(track="IR").count(),
            "CP": documents.filter(track="CP").count(),
            "LGP": documents.filter(track="LGP").count(),
            "ALL": documents.filter(track="ALL").count(),
        },
    }

    # Grade statistics by semester
    semester_stats = []
    semesters = (
        grade_records.values("semester", "year")
        .annotate(total=Count("id"), completed=Count("id", filter=Q(is_completed=True)))
        .order_by("-year", "-semester")[:10]
    )

    for sem in semesters:
        semester_display = (
            "Semester 1" if sem["semester"] == "semester1" else "Semester 2"
        )
        semester_stats.append(
            {
                "semester": sem["semester"],
                "semester_display": semester_display,
                "year": sem["year"],
                "total": sem["total"],
                "completed": sem["completed"],
                "display": f"{semester_display} {sem['year']}",
            }
        )

    data = {
        "student_distribution": student_distribution,
        "grade_distribution": grade_distribution,
        "course_distribution": course_distribution,
        "graduation_rates": graduation_rates,
        "document_stats": document_stats,
        "semester_stats": semester_stats,
    }

    return JsonResponse(data)


# ============== ENHANCED STUDENT REPORT - TRACK-SPECIFIC COURSES ==============
@login_required
@require_http_methods(["GET"])
def enhanced_student_report(request, student_id):
    """Generate comprehensive student report with real-time data and track-specific courses"""
    try:
        student = Student.objects.get(id=student_id)

        progress = calculate_progress(student)
        cgpa = calculate_cgpa(student)
        honors = calculate_honors(cgpa)

        # Get county display name
        county_display = ""
        if student.county:
            for code, name in LIBERIA_COUNTIES:
                if code == student.county:
                    county_display = name
                    break

        # Get all courses
        all_courses = Course.objects.filter(is_active=True)

        # Filter courses based on student's track
        required_courses = []
        major_courses = []
        minor_courses = []
        elective_courses = []

        # Get courses the student has taken (with grades)
        completed_courses_dict = {}
        for course_id, grade in student.completed_courses.items():
            try:
                course = Course.objects.get(id=course_id)
                completed_courses_dict[course_id] = {"course": course, "grade": grade}
            except Course.DoesNotExist:
                continue

        # Get ALL required courses (these are track-independent)
        required_courses_list = all_courses.filter(course_type="required")
        for course in required_courses_list:
            grade = student.completed_courses.get(str(course.id), "IP")
            # Get grade record details if available
            grade_record = GradeRecord.objects.filter(
                student=student, course=course
            ).first()

            required_courses.append(
                {
                    "id": course.id,
                    "code": course.code,
                    "title": course.title,
                    "credits": course.credits,
                    "grade": grade,
                    "semester": grade_record.semester if grade_record else None,
                    "year": grade_record.year if grade_record else None,
                    "status": (
                        "Completed" if grade not in ["IP", None] else "In Progress"
                    ),
                }
            )

        # Get major courses based on student's track
        if student.track:
            # Major courses: must match student's track OR have track="ALL"
            major_courses_list = all_courses.filter(course_type="major").filter(
                Q(track=student.track) | Q(track="ALL")
            )
        else:
            # If no track, show all major courses (or none, depending on your logic)
            major_courses_list = all_courses.filter(course_type="major", track="ALL")

        for course in major_courses_list:
            grade = student.completed_courses.get(str(course.id), "IP")
            grade_record = GradeRecord.objects.filter(
                student=student, course=course
            ).first()

            major_courses.append(
                {
                    "id": course.id,
                    "code": course.code,
                    "title": course.title,
                    "credits": course.credits,
                    "grade": grade,
                    "track": course.track,
                    "semester": grade_record.semester if grade_record else None,
                    "year": grade_record.year if grade_record else None,
                    "status": (
                        "Completed" if grade not in ["IP", None] else "In Progress"
                    ),
                }
            )

        # Get minor courses (if student has a track)
        if student.track:
            minor_courses_list = StudentMinor.objects.filter(
                student=student
            ).select_related("course")
            for sm in minor_courses_list:
                minor_courses.append(
                    {
                        "id": sm.course.id,
                        "code": sm.course.code,
                        "title": sm.course.title,
                        "credits": sm.course.credits,
                        "grade": sm.grade or "IP",
                        "semester": sm.semester,
                        "year": sm.year,
                        "status": (
                            "Completed"
                            if sm.grade not in ["IP", None]
                            else "In Progress"
                        ),
                    }
                )
        else:
            # If no track, show all minor courses or none
            minor_courses = []

        # Get elective courses
        if student.track:
            elective_courses_list = StudentElective.objects.filter(
                student=student
            ).select_related("course")
            for se in elective_courses_list:
                elective_courses.append(
                    {
                        "id": se.course.id,
                        "code": se.course.code,
                        "title": se.course.title,
                        "credits": se.course.credits,
                        "grade": se.grade or "IP",
                        "semester": se.semester,
                        "year": se.year,
                        "status": (
                            "Completed"
                            if se.grade not in ["IP", None]
                            else "In Progress"
                        ),
                    }
                )

        # Get department info
        dept_info = {
            "name": "Department of Political Science",
            "address": "University of Liberia, Capitol Hill, Monrovia, Liberia",
            "phone": "+231 777 123 456",
            "email": "polisci@ul.edu.lr",
            "dean": "Assistant Professor, Richmond S. Anderson",
        }

        data = {
            "student": {
                "id": student.id,
                "student_id": student.student_id,
                "name": student.name,
                "year": student.year,
                "class_standing": get_class_standing(student),
                "program_type": student.program_type,
                "program_type_display": dict(Student.PROGRAM_TYPE_CHOICES).get(
                    student.program_type, "Major"
                ),
                "track": (
                    dict(Student.TRACK_CHOICES).get(student.track, student.track)
                    if student.track
                    else "No Track"
                ),
                "track_code": student.track,
                "nationality": (
                    student.nationality.code if student.nationality else None
                ),
                "nationality_name": (
                    student.nationality.name if student.nationality else None
                ),
                "county": student.county,
                "county_code": student.county,
                "gender": (
                    dict(Student.GENDER_CHOICES).get(student.gender, "")
                    if student.gender
                    else None
                ),
                "gender_code": student.gender,
                "religion": student.religion,
                "date_of_birth": (
                    student.date_of_birth.strftime("%B %d, %Y")
                    if student.date_of_birth
                    else None
                ),
                "status": student.status,
                "photo_url": (
                    student.photo.url
                    if student.photo
                    else (student.photo_url if student.photo_url else None)
                ),
                "department": student.department.name if student.department else None,
                "department_id": student.department_id,
            },
            "dept_info": dept_info,
            "cgpa": round(cgpa, 2),
            "honors_status": honors,
            "progress": progress,
            "required_courses": required_courses,
            "major_courses": major_courses,
            "minor_courses": minor_courses,
            "elective_courses": elective_courses,
            "generated": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        }

        return JsonResponse(data)

    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)


# ============== ENHANCED PDF REPORT GENERATION WITH MODERN DESIGN ==============
@login_required
@require_http_methods(["GET"])
def export_student_pdf(request, student_id):
    """Generate a beautiful modern PDF report for a student using ReportLab"""
    try:
        student = Student.objects.get(id=student_id)

        # Get student data
        progress = calculate_progress(student)
        cgpa = calculate_cgpa(student)
        honors = calculate_honors(cgpa)

        # Get courses by category with track filtering
        all_courses = Course.objects.filter(is_active=True)

        required_courses = []
        major_courses = []
        minor_courses = []
        elective_courses = []

        # Required courses
        required_courses_list = all_courses.filter(course_type="required")
        for course in required_courses_list:
            grade = student.completed_courses.get(str(course.id), "IP")
            grade_record = GradeRecord.objects.filter(
                student=student, course=course
            ).first()

            required_courses.append(
                {
                    "code": course.code,
                    "title": course.title,
                    "credits": course.credits,
                    "grade": grade,
                    "semester": grade_record.semester if grade_record else None,
                    "year": grade_record.year if grade_record else None,
                }
            )

        # Major courses (track-specific)
        if student.track:
            major_courses_list = all_courses.filter(course_type="major").filter(
                Q(track=student.track) | Q(track="ALL")
            )
        else:
            major_courses_list = all_courses.filter(course_type="major", track="ALL")

        for course in major_courses_list:
            grade = student.completed_courses.get(str(course.id), "IP")
            grade_record = GradeRecord.objects.filter(
                student=student, course=course
            ).first()

            major_courses.append(
                {
                    "code": course.code,
                    "title": course.title,
                    "credits": course.credits,
                    "grade": grade,
                    "semester": grade_record.semester if grade_record else None,
                    "year": grade_record.year if grade_record else None,
                    "status": (
                        "Completed" if grade not in ["IP", None] else "In Progress"
                    ),
                }
            )

        # Minor courses
        minor_courses_list = StudentMinor.objects.filter(
            student=student
        ).select_related("course")
        for sm in minor_courses_list:
            minor_courses.append(
                {
                    "code": sm.course.code,
                    "title": sm.course.title,
                    "credits": sm.course.credits,
                    "grade": sm.grade or "IP",
                    "semester": sm.semester,
                    "year": sm.year,
                    "status": (
                        "Completed" if sm.grade not in ["IP", None] else "In Progress"
                    ),
                }
            )

        # Elective courses
        elective_courses_list = StudentElective.objects.filter(
            student=student
        ).select_related("course")
        for se in elective_courses_list:
            elective_courses.append(
                {
                    "code": se.course.code,
                    "title": se.course.title,
                    "credits": se.course.credits,
                    "grade": se.grade or "IP",
                    "semester": se.semester,
                    "year": se.year,
                    "status": (
                        "Completed" if se.grade not in ["IP", None] else "In Progress"
                    ),
                }
            )

        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        # Styles
        styles = getSampleStyleSheet()

        # Custom styles for modern design
        title_style = ParagraphStyle(
            "ModernTitle",
            parent=styles["Heading1"],
            fontSize=28,
            textColor=colors.HexColor("#1e3a8a"),
            alignment=TA_CENTER,
            spaceAfter=10,
            fontName="Helvetica-Bold",
        )

        subtitle_style = ParagraphStyle(
            "ModernSubtitle",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#4b5563"),
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName="Helvetica",
        )

        section_title_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading3"],
            fontSize=16,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=15,
            spaceAfter=8,
            fontName="Helvetica-Bold",
            borderWidth=1,
            borderColor=colors.HexColor("#e5e7eb"),
            borderPadding=5,
            borderRadius=3,
        )

        info_label_style = ParagraphStyle(
            "InfoLabel",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#6b7280"),
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        )

        info_value_style = ParagraphStyle(
            "InfoValue",
            parent=styles["Normal"],
            fontSize=11,
            textColor=colors.HexColor("#111827"),
            fontName="Helvetica",
        )

        # Build PDF content
        story = []

        # Header with institution logo and name
        system_settings = SystemSettings.objects.first()
        institution_name = (
            system_settings.institution_name
            if system_settings
            else "University of Liberia"
        )

        # Try to add logo if exists
        if system_settings and system_settings.site_logo:
            logo_path = system_settings.site_logo.path
            if os.path.exists(logo_path):
                try:
                    logo = Image(logo_path, width=1.5 * inch, height=1.5 * inch)
                    logo.hAlign = TA_CENTER
                    story.append(logo)
                    story.append(Spacer(1, 0.1 * inch))
                except:
                    pass

        story.append(Paragraph(institution_name, title_style))
        story.append(Paragraph("Department of Political Science", subtitle_style))

        # Decorative line
        story.append(Spacer(1, 0.1 * inch))
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[6.5 * inch])
        line_table.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, -1), 2, colors.HexColor("#2563eb")),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ]
            )
        )
        story.append(line_table)
        story.append(Spacer(1, 0.2 * inch))

        # Student Info in a modern grid
        student_info_data = [
            ["Student Name:", student.name, "Student ID:", student.student_id],
            [
                "Class Standing:",
                get_class_standing(student),
                "Track:",
                student.track or "No Track",
            ],
            [
                "Enrollment Year:",
                str(student.year),
                "Program:",
                student.program_type.title() if student.program_type else "Major",
            ],
        ]

        student_info_table = Table(
            student_info_data,
            colWidths=[1.2 * inch, 2.3 * inch, 1.2 * inch, 2.3 * inch],
        )
        student_info_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4b5563")),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#4b5563")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                    ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f9fafb")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                ]
            )
        )
        story.append(student_info_table)
        story.append(Spacer(1, 0.2 * inch))

        # CGPA Card with gradient effect
        cgpa_data = [
            ["", "", "", ""],
            ["Cumulative GPA", f"{cgpa:.2f}", "Honors Status", honors["level"]],
            ["", "", "", ""],
        ]

        cgpa_table = Table(
            cgpa_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch]
        )
        cgpa_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 1), (1, 1), colors.HexColor("#2563eb")),
                    ("BACKGROUND", (2, 1), (3, 1), colors.HexColor("#10b981")),
                    ("TEXTCOLOR", (0, 1), (1, 1), colors.white),
                    ("TEXTCOLOR", (2, 1), (3, 1), colors.white),
                    ("FONTNAME", (0, 1), (1, 1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 1), (3, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 1), (1, 1), 16),
                    ("FONTSIZE", (2, 1), (3, 1), 14),
                    ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                    ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
                    ("TOPPADDING", (0, 1), (-1, 1), 15),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 15),
                    ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                ]
            )
        )
        story.append(cgpa_table)
        story.append(Spacer(1, 0.2 * inch))

        # Progress Bars
        progress_data = [
            [
                "Required",
                f"{progress['required']}/65",
                f"{min(100, int(progress['required']*100/65))}%",
            ],
            [
                "Major",
                f"{progress['major']}/45",
                f"{min(100, int(progress['major']*100/45))}%",
            ],
        ]
        if student.track:
            progress_data.append(
                [
                    "Minor",
                    f"{progress['minor']}/18",
                    f"{min(100, int(progress['minor']*100/18))}%",
                ]
            )
            progress_data.append(
                [
                    "Elective",
                    f"{progress['electives']}/6",
                    f"{min(100, int(progress['electives']*100/6))}%",
                ]
            )

        progress_table = Table(
            progress_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch]
        )
        progress_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ]
            )
        )
        story.append(progress_table)
        story.append(Spacer(1, 0.2 * inch))

        # Function to add course table with modern design
        def add_course_table(title, courses, color):
            if not courses:
                return

            story.append(Paragraph(title, section_title_style))

            # Prepare data for table
            data = [["Code", "Course Title", "Credits", "Grade", "Semester"]]
            for course in courses:
                semester_display = (
                    f"{'Semester 1' if course.get('semester') == 'semester1' else 'Semester 2' if course.get('semester') == 'semester2' else ''} {course.get('year', '')}"
                    if course.get("semester")
                    else "—"
                )
                data.append(
                    [
                        course["code"],
                        course["title"],
                        str(course["credits"]),
                        course["grade"],
                        semester_display,
                    ]
                )

            table = Table(
                data, colWidths=[1 * inch, 3 * inch, 0.6 * inch, 0.8 * inch, 1.1 * inch]
            )
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("ALIGN", (2, 0), (2, -1), "CENTER"),
                        ("ALIGN", (3, 0), (3, -1), "CENTER"),
                        ("ALIGN", (4, 0), (4, -1), "CENTER"),
                        ("BACKGROUND", (0, 0), (-1, 0), color),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )

            # Color code grades
            for i, row in enumerate(data[1:], start=1):
                grade = row[3]
                if grade in ["A", "A-"]:
                    table.setStyle(
                        TableStyle(
                            [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#059669"))]
                        )
                    )
                elif grade in ["B+", "B", "B-"]:
                    table.setStyle(
                        TableStyle(
                            [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#2563eb"))]
                        )
                    )
                elif grade in ["C+", "C"]:
                    table.setStyle(
                        TableStyle(
                            [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#d97706"))]
                        )
                    )
                elif grade in ["D", "F"]:
                    table.setStyle(
                        TableStyle(
                            [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#dc2626"))]
                        )
                    )
                elif grade == "IP":
                    table.setStyle(
                        TableStyle(
                            [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#6b7280"))]
                        )
                    )

            story.append(table)
            story.append(Spacer(1, 0.15 * inch))

        # Add course tables
        if required_courses:
            add_course_table(
                "Required Core Courses", required_courses, colors.HexColor("#dc2626")
            )
        if major_courses:
            track_name = student.track or "General"
            add_course_table(
                f"Major Courses - {track_name}",
                major_courses,
                colors.HexColor("#2563eb"),
            )
        if minor_courses:
            add_course_table("Minor Courses", minor_courses, colors.HexColor("#059669"))
        if elective_courses:
            add_course_table(
                "Elective Courses", elective_courses, colors.HexColor("#7c3aed")
            )

        # Summary statistics
        story.append(Spacer(1, 0.2 * inch))
        summary_data = [
            [
                "Total Credits Earned:",
                str(progress["completed_credits"]),
                "Required Credits:",
                "134",
            ],
            [
                "Overall Progress:",
                f"{progress['percent_complete']}%",
                "Graduation Eligibility:",
                "Eligible" if progress["percent_complete"] >= 95 else "In Progress",
            ],
        ]

        summary_table = Table(
            summary_data, colWidths=[1.5 * inch, 1 * inch, 1.5 * inch, 1.5 * inch]
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4b5563")),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#4b5563")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("ALIGN", (3, 0), (3, -1), "CENTER"),
                ]
            )
        )
        story.append(summary_table)

        # Footer with signature
        story.append(Spacer(1, 0.5 * inch))
        footer_data = [
            ["Generated on:", datetime.now().strftime("%B %d, %Y at %I:%M %p"), "", ""],
            ["Department of Political Science", "University of Liberia", "", ""],
            ["", "", "Assistant Professor, Richmond S. Anderson", "Department Chair"],
        ]

        footer_table = Table(
            footer_data, colWidths=[2 * inch, 2.5 * inch, 1.5 * inch, 1 * inch]
        )
        footer_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#6b7280")),
                    ("ALIGN", (2, 2), (3, 2), "RIGHT"),
                    ("LINEABOVE", (2, 2), (3, 2), 1, colors.HexColor("#2563eb")),
                ]
            )
        )
        story.append(footer_table)

        # Build PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # Return PDF response
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{student.student_id}_academic_report_{datetime.now().strftime("%Y%m%d")}.pdf"'
        )
        return response

    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)


# ============== EXPORT ALL STUDENTS PDF ==============
@login_required
@require_http_methods(["GET"])
def export_all_students_pdf(request):
    """Generate a beautiful PDF report for all students"""
    try:
        students = Student.objects.all().order_by("name")

        # Get filter parameters
        track = request.GET.get("track")
        status = request.GET.get("status")

        if track:
            students = students.filter(track=track)
        if status:
            students = students.filter(status=status)

        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=36,
            leftMargin=36,
            topMargin=54,
            bottomMargin=54,
        )

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ModernTitle",
            parent=styles["Heading1"],
            fontSize=22,
            textColor=colors.HexColor("#1e3a8a"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "ModernSubtitle",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#4b5563"),
            alignment=TA_CENTER,
            spaceAfter=15,
        )

        # Build PDF content
        story = []

        # Header
        system_settings = SystemSettings.objects.first()
        institution_name = (
            system_settings.institution_name
            if system_settings
            else "University of Liberia"
        )

        story.append(Paragraph(institution_name, title_style))
        story.append(
            Paragraph(
                "Department of Political Science - Student Directory", subtitle_style
            )
        )
        story.append(
            Paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
                styles["Normal"],
            )
        )

        # Filter info
        filter_info = []
        if track:
            filter_info.append(f"Track: {track}")
        if status:
            filter_info.append(f"Status: {status}")
        if filter_info:
            story.append(
                Paragraph(f"Filters: {' | '.join(filter_info)}", styles["Italic"])
            )

        story.append(Spacer(1, 0.2 * inch))

        # Students table
        data = [
            ["ID", "Name", "Class", "Program", "Track", "CGPA", "Progress", "Status"]
        ]

        for student in students:
            cgpa = calculate_cgpa(student)
            progress = calculate_progress(student)

            data.append(
                [
                    student.student_id,
                    (
                        student.name[:30] + "..."
                        if len(student.name) > 30
                        else student.name
                    ),
                    get_class_standing(student),
                    student.program_type.title() if student.program_type else "Major",
                    student.track or "No Track",
                    f"{cgpa:.2f}",
                    f"{progress['percent_complete']}%",
                    student.status.title(),
                ]
            )

        table = Table(
            data,
            colWidths=[
                1 * inch,
                2.2 * inch,
                0.8 * inch,
                0.8 * inch,
                1.2 * inch,
                0.8 * inch,
                0.8 * inch,
                1 * inch,
            ],
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (5, 1), (6, -1), "CENTER"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f9fafb")],
                    ),
                ]
            )
        )

        story.append(table)

        # Footer with stats
        story.append(Spacer(1, 0.2 * inch))
        total_students = students.count()
        active_students = students.filter(status="active").count()
        graduated_students = students.filter(status="graduated").count()

        stats_data = [
            [
                "Total Students:",
                str(total_students),
                "Active:",
                str(active_students),
                "Graduated:",
                str(graduated_students),
            ]
        ]

        stats_table = Table(
            stats_data,
            colWidths=[
                1.2 * inch,
                0.8 * inch,
                1 * inch,
                0.8 * inch,
                1 * inch,
                0.8 * inch,
            ],
        )
        stats_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                    ("ALIGN", (1, 0), (1, 0), "LEFT"),
                    ("ALIGN", (3, 0), (3, 0), "LEFT"),
                    ("ALIGN", (5, 0), (5, 0), "LEFT"),
                ]
            )
        )

        story.append(stats_table)

        # Build PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # Return PDF response
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="student_directory_{datetime.now().strftime("%Y%m%d")}.pdf"'
        )
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== EXPORT COURSES PDF ==============
@login_required
@require_http_methods(["GET"])
def export_courses_pdf(request):
    """Generate a beautiful PDF report for all courses"""
    try:
        courses = Course.objects.filter(is_active=True).order_by("code")

        # Apply filters
        course_type = request.GET.get("type")
        track = request.GET.get("track")
        dept_id = request.GET.get("dept")

        if course_type:
            courses = courses.filter(course_type=course_type)
        if track:
            courses = courses.filter(track=track)
        if dept_id:
            courses = courses.filter(department_id=dept_id)

        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=36,
            leftMargin=36,
            topMargin=54,
            bottomMargin=54,
        )

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ModernTitle",
            parent=styles["Heading1"],
            fontSize=22,
            textColor=colors.HexColor("#1e3a8a"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )

        # Build PDF content
        story = []

        # Header
        system_settings = SystemSettings.objects.first()
        institution_name = (
            system_settings.institution_name
            if system_settings
            else "University of Liberia"
        )

        story.append(Paragraph(institution_name, title_style))
        story.append(
            Paragraph(
                "Department of Political Science - Course Catalog", styles["Heading2"]
            )
        )
        story.append(
            Paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
                styles["Normal"],
            )
        )

        # Filter info
        filter_info = []
        if course_type:
            filter_info.append(f"Type: {course_type}")
        if track:
            filter_info.append(f"Track: {track}")
        if filter_info:
            story.append(
                Paragraph(f"Filters: {' | '.join(filter_info)}", styles["Italic"])
            )

        story.append(Spacer(1, 0.2 * inch))

        # Course statistics
        total_courses = courses.count()
        total_credits = courses.aggregate(Sum("credits"))["credits__sum"] or 0

        stats_data = [
            ["Total Courses:", str(total_courses), "Total Credits:", str(total_credits)]
        ]

        stats_table = Table(
            stats_data, colWidths=[1.5 * inch, 1 * inch, 1.5 * inch, 1 * inch]
        )
        stats_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                    ("ALIGN", (1, 0), (1, 0), "LEFT"),
                    ("ALIGN", (3, 0), (3, 0), "LEFT"),
                    ("ALIGN", (5, 0), (5, 0), "LEFT"),
                ]
            )
        )
        story.append(stats_table)
        story.append(Spacer(1, 0.2 * inch))

        # Courses table
        data = [["Code", "Title", "Credits", "Type", "Track", "Department", "Category"]]

        for course in courses:
            data.append(
                [
                    course.code,
                    (
                        course.title[:35] + "..."
                        if len(course.title) > 35
                        else course.title
                    ),
                    str(course.credits),
                    course.course_type.title(),
                    course.track or "ALL",
                    course.department.name if course.department else "—",
                    course.category.name if course.category else "—",
                ]
            )

        table = Table(
            data,
            colWidths=[
                1 * inch,
                2.5 * inch,
                0.6 * inch,
                1 * inch,
                1 * inch,
                1.2 * inch,
                1.2 * inch,
            ],
        )
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f9fafb")],
                    ),
                    ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ]
            )
        )

        story.append(table)

        # Build PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # Return PDF response
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="course_catalog_{datetime.now().strftime("%Y%m%d")}.pdf"'
        )
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== EXPORT GRADUATES PDF ==============
@login_required
@require_http_methods(["GET"])
def export_graduates_pdf(request):
    """Generate a beautiful PDF report for graduated students"""
    try:
        graduates = Student.objects.filter(status="graduated").order_by("-year", "name")

        # Apply filters
        year = request.GET.get("year")
        track = request.GET.get("track")

        if year:
            graduates = graduates.filter(year=year)
        if track:
            graduates = graduates.filter(track=track)

        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=36,
            leftMargin=36,
            topMargin=54,
            bottomMargin=54,
        )

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ModernTitle",
            parent=styles["Heading1"],
            fontSize=22,
            textColor=colors.HexColor("#1e3a8a"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )

        # Build PDF content
        story = []

        # Header
        system_settings = SystemSettings.objects.first()
        institution_name = (
            system_settings.institution_name
            if system_settings
            else "University of Liberia"
        )

        story.append(Paragraph(institution_name, title_style))
        story.append(
            Paragraph(
                "Department of Political Science - Graduates Report", styles["Heading2"]
            )
        )
        story.append(
            Paragraph(
                f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # Statistics
        total_graduates = graduates.count()
        ir_graduates = graduates.filter(track="IR").count()
        cp_graduates = graduates.filter(track="CP").count()
        lgp_graduates = graduates.filter(track="LGP").count()

        stats_data = [
            [
                "Total Graduates:",
                str(total_graduates),
                "IR:",
                str(ir_graduates),
                "CP:",
                str(cp_graduates),
                "LGP:",
                str(lgp_graduates),
            ]
        ]

        stats_table = Table(
            stats_data,
            colWidths=[
                1.2 * inch,
                0.8 * inch,
                0.8 * inch,
                0.8 * inch,
                0.8 * inch,
                0.8 * inch,
                0.8 * inch,
                0.8 * inch,
            ],
        )
        stats_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
                ]
            )
        )
        story.append(stats_table)
        story.append(Spacer(1, 0.2 * inch))

        # Group by year
        years = graduates.values_list("year", flat=True).distinct().order_by("-year")

        for year in years:
            year_graduates = graduates.filter(year=year)
            story.append(Paragraph(f"Class of {year}", styles["Heading3"]))

            data = [["ID", "Name", "Track", "Final CGPA"]]

            for grad in year_graduates:
                cgpa = calculate_cgpa(grad)
                data.append(
                    [
                        grad.student_id,
                        grad.name,
                        grad.track or "No Track",
                        f"{cgpa:.2f}",
                    ]
                )

            table = Table(data, colWidths=[1.2 * inch, 3 * inch, 1.5 * inch, 1 * inch])
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#059669")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f9fafb")],
                        ),
                    ]
                )
            )

            story.append(table)
            story.append(Spacer(1, 0.1 * inch))

        # Build PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # Return PDF response
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="graduates_{datetime.now().strftime("%Y%m%d")}.pdf"'
        )
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== NOTIFICATIONS API ==============
@login_required
@require_http_methods(["GET"])
def get_notifications(request):
    """Get user notifications"""
    notifications = []

    # Recent grades
    recent_grades_count = GradeRecord.objects.filter(
        date_recorded__gte=timezone.now() - timezone.timedelta(days=7)
    ).count()

    if recent_grades_count > 0:
        notifications.append(
            {
                "id": 1,
                "type": "grade",
                "message": f"{recent_grades_count} new grades submitted this week",
                "icon": "fa-graduation-cap",
                "time": "Just now",
                "read": False,
            }
        )

    # Graduation ready count
    ready_count = 0
    for student in Student.objects.filter(status="active"):
        progress = calculate_progress(student)
        if progress["percent_complete"] >= 95:
            ready_count += 1

    if ready_count > 0:
        notifications.append(
            {
                "id": 2,
                "type": "audit",
                "message": f"{ready_count} students ready for graduation",
                "icon": "fa-check-circle",
                "time": "2 hours ago",
                "read": False,
            }
        )

    # New books by track
    new_books = LibraryBook.objects.filter(
        uploaded_at__date=timezone.now().date()
    ).count()
    if new_books > 0:
        notifications.append(
            {
                "id": 3,
                "type": "library",
                "message": f"{new_books} new books added today",
                "icon": "fa-book",
                "time": "Today",
                "read": True,
            }
        )

    # New documents by track
    new_docs = DepartmentDocument.objects.filter(
        uploaded_at__date=timezone.now().date()
    ).count()
    if new_docs > 0:
        notifications.append(
            {
                "id": 4,
                "type": "document",
                "message": f"{new_docs} new documents uploaded",
                "icon": "fa-file-alt",
                "time": "Today",
                "read": False,
            }
        )

    return JsonResponse(notifications, safe=False)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def mark_notification_read(request):
    """Mark notification as read"""
    try:
        data = json.loads(request.body)
        notification_id = data.get("id")
        # In a real app, update database
        return JsonResponse({"message": "Notification marked as read"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== EXPORT FUNCTIONS (JSON) ==============
@login_required
@require_http_methods(["GET"])
def export_student_report_json(request, student_id):
    """Generate JSON report for a student"""
    try:
        student = Student.objects.get(id=student_id)

        # Calculate progress
        progress = calculate_progress(student)

        # Get course details
        courses_data = []
        for course_id, grade in student.completed_courses.items():
            try:
                course = Course.objects.get(id=course_id)
                grade_record = GradeRecord.objects.filter(
                    student=student, course=course
                ).first()

                courses_data.append(
                    {
                        "code": course.code,
                        "title": course.title,
                        "credits": course.credits,
                        "grade": grade,
                        "semester": grade_record.semester if grade_record else None,
                        "year": grade_record.year if grade_record else None,
                        "category": course.category.name if course.category else None,
                        "course_type": course.course_type,
                    }
                )
            except Course.DoesNotExist:
                continue

        # Get county display name
        county_display = ""
        if student.county:
            for code, name in LIBERIA_COUNTIES:
                if code == student.county:
                    county_display = name
                    break

        data = {
            "student": {
                "id": student.student_id,
                "name": student.name,
                "year": student.year,
                "program_type": student.program_type,
                "track": student.track,
                "nationality": (
                    student.nationality.code if student.nationality else None
                ),
                "nationality_name": (
                    student.nationality.name if student.nationality else None
                ),
                "county": student.county,
                "county_display": county_display,
                "gender": student.gender,
                "religion": student.religion,
                "status": student.status,
            },
            "progress": progress,
            "courses": courses_data,
            "generated": datetime.now().isoformat(),
        }

        return JsonResponse(data)
    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)


# ============== SEARCH/UTILITY API ==============
@login_required
@require_http_methods(["GET"])
def search_courses(request):
    """Search courses by code or title"""
    query = request.GET.get("q", "")
    if len(query) < 2:
        return JsonResponse([], safe=False)

    courses = Course.objects.filter(
        Q(code__icontains=query) | Q(title__icontains=query), is_active=True
    )[:10].values("id", "code", "title", "credits", "course_type", "track")

    results = list(courses)

    return JsonResponse(results, safe=False)


@login_required
@require_http_methods(["GET"])
def get_student_progress(request, student_id):
    """Get detailed progress for a specific student"""
    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return JsonResponse({"error": "Student not found"}, status=404)

    progress = calculate_progress(student)

    data = {
        "student": {
            "id": student.student_id,
            "name": student.name,
            "track": student.track,
        },
        "progress": progress,
    }

    return JsonResponse(data)


# ============== GET SEMESTERS AND YEARS FOR FILTERS ==============
@login_required
@require_http_methods(["GET"])
def get_semester_filters(request):
    """Get distinct semesters and years for filter dropdowns"""
    try:
        semesters = GradeRecord.objects.values_list("semester", flat=True).distinct()
        years = (
            GradeRecord.objects.values_list("year", flat=True)
            .distinct()
            .order_by("-year")
        )

        semester_list = [s for s in semesters if s]
        year_list = [y for y in years if y]

        # Also get from StudentMinor and StudentElective
        minor_semesters = StudentMinor.objects.values_list(
            "semester", flat=True
        ).distinct()
        minor_years = StudentMinor.objects.values_list("year", flat=True).distinct()

        elective_semesters = StudentElective.objects.values_list(
            "semester", flat=True
        ).distinct()
        elective_years = StudentElective.objects.values_list(
            "year", flat=True
        ).distinct()

        # Combine all
        all_semesters = set(
            list(semester_list) + list(minor_semesters) + list(elective_semesters)
        )
        all_years = set(list(year_list) + list(minor_years) + list(elective_years))

        # Remove None/empty
        all_semesters = [s for s in all_semesters if s]
        all_years = sorted([y for y in all_years if y], reverse=True)

        semester_display = []
        for sem in all_semesters:
            display = (
                "Semester 1"
                if sem == "semester1"
                else "Semester 2" if sem == "semester2" else sem.title()
            )
            semester_display.append({"value": sem, "label": display})

        return JsonResponse({"semesters": semester_display, "years": all_years})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== GET COUNTRIES LIST ==============
@login_required
@require_http_methods(["GET"])
def get_countries(request):
    """Get list of all countries for dropdown"""
    country_list = [{"code": code, "name": name} for code, name in list(countries)]
    return JsonResponse(country_list, safe=False)


# ============== GET LIBERIA COUNTIES LIST ==============
@login_required
@require_http_methods(["GET"])
def get_liberia_counties(request):
    """Get list of Liberia counties for dropdown"""
    county_list = [{"code": code, "name": name} for code, name in LIBERIA_COUNTIES]
    return JsonResponse(county_list, safe=False)


# ============== GET PROGRAM TYPES ==============
@login_required
@require_http_methods(["GET"])
def get_program_types(request):
    """Get list of program types (major/minor)"""
    program_types = [
        {"code": "major", "name": "Major"},
        {"code": "minor", "name": "Minor"},
    ]
    return JsonResponse(program_types, safe=False)


# ============== GET GENDER OPTIONS ==============
@login_required
@require_http_methods(["GET"])
def get_gender_options(request):
    """Get list of gender options"""
    genders = [
        {"code": "M", "name": "Male"},
        {"code": "F", "name": "Female"},
        {"code": "O", "name": "Other"},
    ]
    return JsonResponse(genders, safe=False)


# ============== GET RELIGION OPTIONS ==============
@login_required
@require_http_methods(["GET"])
def get_religion_options(request):
    """Get list of religion options"""
    religions = [
        {"code": "Christianity", "name": "Christianity"},
        {"code": "Islam", "name": "Islam"},
        {"code": "Traditional", "name": "Traditional African Religion"},
        {"code": "Other", "name": "Other"},
        {"code": "None", "name": "None"},
    ]
    return JsonResponse(religions, safe=False)


# ============== DEPARTMENT COURSE ASSIGNMENT ==============
@login_required
@require_http_methods(["GET"])
def department_courses(request, dept_id):
    """Get courses assigned to a department with their track information"""
    try:
        department = Department.objects.get(id=dept_id)
        courses = Course.objects.filter(department=department, is_active=True)

        # Group courses by type
        major_courses = courses.filter(course_type="major")
        minor_courses = courses.filter(course_type="minor")
        elective_courses = courses.filter(course_type="elective")
        required_courses = courses.filter(course_type="required")

        result = {
            "department": {
                "id": department.id,
                "name": department.name,
                "code": department.code,
            },
            "courses": {
                "major": [
                    {
                        "id": c.id,
                        "code": c.code,
                        "title": c.title,
                        "credits": c.credits,
                        "track": c.track,
                        "category_id": c.category_id,
                        "category_name": c.category.name if c.category else None,
                    }
                    for c in major_courses
                ],
                "minor": [
                    {
                        "id": c.id,
                        "code": c.code,
                        "title": c.title,
                        "credits": c.credits,
                        "track": c.track,
                        "category_id": c.category_id,
                        "category_name": c.category.name if c.category else None,
                    }
                    for c in minor_courses
                ],
                "elective": [
                    {
                        "id": c.id,
                        "code": c.code,
                        "title": c.title,
                        "credits": c.credits,
                        "track": c.track,
                        "category_id": c.category_id,
                        "category_name": c.category.name if c.category else None,
                    }
                    for c in elective_courses
                ],
                "required": [
                    {
                        "id": c.id,
                        "code": c.code,
                        "title": c.title,
                        "credits": c.credits,
                        "track": c.track,
                        "category_id": c.category_id,
                        "category_name": c.category.name if c.category else None,
                    }
                    for c in required_courses
                ],
            },
            "stats": {
                "major_count": major_courses.count(),
                "minor_count": minor_courses.count(),
                "elective_count": elective_courses.count(),
                "required_count": required_courses.count(),
                "major_credits": sum(c.credits for c in major_courses),
                "minor_credits": sum(c.credits for c in minor_courses),
                "elective_credits": sum(c.credits for c in elective_courses),
                "required_credits": sum(c.credits for c in required_courses),
            },
        }

        return JsonResponse(result)
    except Department.DoesNotExist:
        return JsonResponse({"error": "Department not found"}, status=404)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def assign_department_courses(request, dept_id):
    """Assign courses to a department with track information"""
    try:
        department = Department.objects.get(id=dept_id)
        data = json.loads(request.body)

        required_ids = data.get("required_ids", [])
        major_ids = data.get("major_ids", [])
        minor_ids = data.get("minor_ids", [])
        elective_ids = data.get("elective_ids", [])
        track = data.get("track", "ALL")

        # Update required courses
        Course.objects.filter(id__in=required_ids).update(
            department=department,
            course_type="required",
            track=track if department.code == "POLS" else "ALL",
        )

        # Update major courses
        Course.objects.filter(id__in=major_ids).update(
            department=department,
            course_type="major",
            track=track if department.code == "POLS" else "ALL",
        )

        # Update minor courses
        Course.objects.filter(id__in=minor_ids).update(
            department=department,
            course_type="minor",
            track=track if department.code == "POLS" else "ALL",
        )

        # Update elective courses
        Course.objects.filter(id__in=elective_ids).update(
            department=department,
            course_type="elective",
            track=track if department.code == "POLS" else "ALL",
        )

        # Calculate totals for response
        minor_courses = Course.objects.filter(
            department=department, course_type="minor"
        )
        minor_total_credits = sum(c.credits for c in minor_courses)

        elective_courses = Course.objects.filter(
            department=department, course_type="elective"
        )
        elective_total_credits = sum(c.credits for c in elective_courses)

        warnings = []

        # Validate minor courses (must be max 18 credits)
        if minor_total_credits > 18:
            warnings.append(
                f"Minor courses exceed 18 credits (currently {minor_total_credits})."
            )

        # Validate elective courses (must be max 6 credits)
        if elective_total_credits > 6:
            warnings.append(
                f"Elective courses exceed 6 credits (currently {elective_total_credits})."
            )

        return JsonResponse(
            {
                "message": "Courses assigned successfully",
                "counts": {
                    "required": len(required_ids),
                    "major": len(major_ids),
                    "minor": len(minor_ids),
                    "elective": len(elective_ids),
                },
                "credits": {
                    "minor": minor_total_credits,
                    "elective": elective_total_credits,
                },
                "warnings": warnings,
                "department": department.name,
            }
        )

    except Department.DoesNotExist:
        return JsonResponse({"error": "Department not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== VIEW PDF ==============
@login_required
@require_http_methods(["GET"])
def view_pdf(request, book_id):
    """View PDF in browser"""
    try:
        book = LibraryBook.objects.get(id=book_id)
        book.view_count += 1
        book.save()

        if book.pdf_file:
            file_path = book.pdf_file.path
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="application/pdf")
                    response["Content-Disposition"] = (
                        f'inline; filename="{book.title}.pdf"'
                    )
                    return response
            else:
                return JsonResponse({"error": "File not found"}, status=404)
        elif book.pdf_url:
            return redirect(book.pdf_url)
        else:
            return JsonResponse({"error": "No PDF available"}, status=404)
    except LibraryBook.DoesNotExist:
        return JsonResponse({"error": "Book not found"}, status=404)


@login_required
@require_http_methods(["GET"])
def download_pdf(request, book_id):
    """Download PDF file"""
    try:
        book = LibraryBook.objects.get(id=book_id)
        book.download_count += 1
        book.save()

        if book.pdf_file:
            file_path = book.pdf_file.path
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="application/pdf")
                    response["Content-Disposition"] = (
                        f'attachment; filename="{book.title}.pdf"'
                    )
                    return response
            else:
                return JsonResponse({"error": "File not found"}, status=404)
        else:
            return JsonResponse({"error": "No PDF file available"}, status=404)
    except LibraryBook.DoesNotExist:
        return JsonResponse({"error": "Book not found"}, status=404)


# ============== VIEW DOCUMENT ==============
@login_required
@require_http_methods(["GET"])
def view_document(request, document_id):
    """View document in browser"""
    try:
        document = DepartmentDocument.objects.get(id=document_id)

        if document.file:
            file_path = document.file.path
            if os.path.exists(file_path):
                if document.document_type == "pdf":
                    with open(file_path, "rb") as f:
                        response = HttpResponse(
                            f.read(), content_type="application/pdf"
                        )
                        response["Content-Disposition"] = (
                            f'inline; filename="{document.title}.pdf"'
                        )
                        return response
                elif document.document_type == "image":
                    with open(file_path, "rb") as f:
                        content_type = f'image/{file_path.split(".")[-1].lower()}'
                        response = HttpResponse(f.read(), content_type=content_type)
                        response["Content-Disposition"] = (
                            f'inline; filename="{document.title}"'
                        )
                        return response
                else:
                    # For Word docs, redirect to Google Docs viewer
                    file_url = request.build_absolute_uri(document.file.url)
                    return redirect(
                        f"https://docs.google.com/viewer?url={file_url}&embedded=true"
                    )
            else:
                return JsonResponse({"error": "File not found"}, status=404)
        else:
            return JsonResponse({"error": "No file available"}, status=404)
    except DepartmentDocument.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)


@login_required
@require_http_methods(["GET"])
def download_document(request, document_id):
    """Download document file"""
    try:
        document = DepartmentDocument.objects.get(id=document_id)
        document.download_count += 1
        document.save()

        if document.file:
            file_path = document.file.path
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    content_type, encoding = mimetypes.guess_type(file_path)
                    if not content_type:
                        content_type = "application/octet-stream"

                    response = HttpResponse(f.read(), content_type=content_type)
                    response["Content-Disposition"] = (
                        f'attachment; filename="{document.title}.{file_path.split(".")[-1]}"'
                    )
                    return response
            else:
                return JsonResponse({"error": "File not found"}, status=404)
        else:
            return JsonResponse({"error": "No file available"}, status=404)
    except DepartmentDocument.DoesNotExist:
        return JsonResponse({"error": "Document not found"}, status=404)


# Add these new view functions to your views.py


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def upload_signature(request):
    """Handle signature upload for chairman"""
    try:
        # Check if user is chairman
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        signature_file = request.FILES.get("signature")
        if not signature_file:
            return JsonResponse({"error": "No signature file provided"}, status=400)

        # Validate file type
        allowed_types = [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/jpg",
            "image/svg+xml",
        ]
        if signature_file.content_type not in allowed_types:
            return JsonResponse(
                {"error": "File must be an image (JPEG, PNG, GIF, SVG)"}, status=400
            )

        # Create signatures directory if it doesn't exist
        signatures_dir = os.path.join(settings.MEDIA_ROOT, "signatures")
        os.makedirs(signatures_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"signature_{timestamp}.{signature_file.name.split('.')[-1]}"

        # Save file
        fs = FileSystemStorage(location=signatures_dir)
        filename = fs.save(filename, signature_file)
        signature_url = f"{settings.MEDIA_URL}signatures/{filename}"

        # Update settings
        settings_obj, created = SystemSettings.objects.get_or_create(id=1)

        # Store signature path
        if not hasattr(settings_obj, "chairman_signature"):
            # If field doesn't exist in model, we need to add it
            # For now, we'll store in a JSON field or add to model later
            # This is a temporary solution
            if not hasattr(settings_obj, "additional_settings"):
                settings_obj.additional_settings = {}
            else:
                if not settings_obj.additional_settings:
                    settings_obj.additional_settings = {}

            settings_obj.additional_settings["chairman_signature"] = (
                f"signatures/{filename}"
            )
        else:
            settings_obj.chairman_signature = f"signatures/{filename}"

        settings_obj.save()

        return JsonResponse(
            {
                "message": "Signature uploaded successfully",
                "signature_url": signature_url,
                "filename": filename,
            }
        )

    except Exception as e:
        print(f"Error in upload_signature: {str(e)}")
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def save_signature_settings(request):
    """Save signature settings including chairman name and title"""
    try:
        # Check if user is chairman
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        data = json.loads(request.body)
        chairman_name = data.get("chairman_name")
        chairman_title = data.get("chairman_title")
        department_logo = data.get("department_logo")
        chairman_signature = data.get("chairman_signature")

        # Update settings
        settings_obj, created = SystemSettings.objects.get_or_create(id=1)

        # Store chairman name and title
        if not hasattr(settings_obj, "chairman_name"):
            if not hasattr(settings_obj, "additional_settings"):
                settings_obj.additional_settings = {}
            else:
                if not settings_obj.additional_settings:
                    settings_obj.additional_settings = {}

            if chairman_name:
                settings_obj.additional_settings["chairman_name"] = chairman_name
            if chairman_title:
                settings_obj.additional_settings["chairman_title"] = chairman_title
            if department_logo:
                settings_obj.additional_settings["department_logo"] = department_logo
            if chairman_signature:
                settings_obj.additional_settings["chairman_signature"] = (
                    chairman_signature
                )
        else:
            if chairman_name:
                settings_obj.chairman_name = chairman_name
            if chairman_title:
                settings_obj.chairman_title = chairman_title
            if department_logo and hasattr(settings_obj, "department_logo"):
                settings_obj.department_logo = department_logo
            if chairman_signature and hasattr(settings_obj, "chairman_signature"):
                settings_obj.chairman_signature = chairman_signature

        settings_obj.save()

        return JsonResponse(
            {
                "message": "Signature settings saved successfully",
                "chairman_name": chairman_name,
                "chairman_title": chairman_title,
            }
        )

    except Exception as e:
        print(f"Error in save_signature_settings: {str(e)}")
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


# ============== FILE UPLOAD FOR PROFILE PHOTOS ==============
@login_required
@require_http_methods(["POST"])
@csrf_exempt
def upload_profile_photo(request):
    """Handle profile photo upload for students and teachers"""
    try:
        # Log the request for debugging
        print("=" * 50)
        print("Photo upload request received")
        print("POST data:", request.POST)
        print("FILES:", request.FILES)
        print("Content-Type:", request.content_type)

        # Check if it's multipart form data
        if (
            not request.content_type
            or "multipart/form-data" not in request.content_type
        ):
            return JsonResponse(
                {
                    "error": "Content-Type must be multipart/form-data",
                    "received": request.content_type,
                },
                status=400,
            )

        entity_type = request.POST.get("entity_type")
        entity_id = request.POST.get("entity_id")
        photo_file = request.FILES.get("photo")

        # Validate required fields
        if not entity_type:
            return JsonResponse({"error": "entity_type is required"}, status=400)

        if not entity_id:
            return JsonResponse({"error": "entity_id is required"}, status=400)

        if not photo_file:
            return JsonResponse({"error": "No photo file provided"}, status=400)

        print(f"Entity Type: {entity_type}, Entity ID: {entity_id}")
        print(
            f"File name: {photo_file.name}, Size: {photo_file.size}, Content Type: {photo_file.content_type}"
        )

        # Validate entity type
        if entity_type not in ["student", "teacher"]:
            return JsonResponse(
                {"error": 'Invalid entity type. Must be "student" or "teacher"'},
                status=400,
            )

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/jpg"]
        if photo_file.content_type not in allowed_types:
            return JsonResponse(
                {
                    "error": f"File must be JPEG, PNG, or GIF. Received: {photo_file.content_type}"
                },
                status=400,
            )

        # Validate file size (max 5MB)
        max_size = 5 * 1024 * 1024  # 5MB
        if photo_file.size > max_size:
            return JsonResponse(
                {
                    "error": f"File too large. Maximum size is 5MB. Received: {photo_file.size / 1024 / 1024:.1f}MB"
                },
                status=400,
            )

        # Create profile_photos directory if it doesn't exist
        photos_dir = os.path.join(settings.MEDIA_ROOT, "profile_photos")
        os.makedirs(photos_dir, exist_ok=True)
        print(f"Photos directory: {photos_dir}")

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = photo_file.name.split(".")[-1].lower()
        safe_filename = f"{entity_type}_{entity_id}_{timestamp}.{file_extension}"
        # Remove any unsafe characters
        safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in "._-")
        print(f"Saving as: {safe_filename}")

        # Save file
        file_path = os.path.join(photos_dir, safe_filename)
        with open(file_path, "wb+") as destination:
            for chunk in photo_file.chunks():
                destination.write(chunk)

        print(f"File saved to: {file_path}")

        # Create relative path for database
        relative_path = f"profile_photos/{safe_filename}"
        photo_url = f"{settings.MEDIA_URL}profile_photos/{safe_filename}"

        # Update entity - LOOKUP BY student_id/teacher_id INSTEAD OF UUID
        if entity_type == "student":
            try:
                # Try to find by student_id field (the string ID)
                student = Student.objects.get(student_id=entity_id)
                student.photo = relative_path
                student.photo_url = photo_url
                student.save()
                print(f"Updated student: {student.name}")
            except Student.DoesNotExist:
                # Try with UUID if it's a valid UUID
                try:
                    student = Student.objects.get(id=entity_id)
                    student.photo = relative_path
                    student.photo_url = photo_url
                    student.save()
                    print(f"Updated student by UUID: {student.name}")
                except (Student.DoesNotExist, ValueError):
                    os.remove(file_path)  # Clean up uploaded file
                    return JsonResponse(
                        {"error": f"Student not found with ID: {entity_id}"}, status=404
                    )

        elif entity_type == "teacher":
            try:
                # Try to find by teacher_id field (the string ID)
                teacher = Teacher.objects.get(teacher_id=entity_id)
                teacher.photo = relative_path
                teacher.photo_url = photo_url
                teacher.save()
                print(f"Updated teacher: {teacher.name}")
            except Teacher.DoesNotExist:
                # Try with UUID if it's a valid UUID
                try:
                    teacher = Teacher.objects.get(id=entity_id)
                    teacher.photo = relative_path
                    teacher.photo_url = photo_url
                    teacher.save()
                    print(f"Updated teacher by UUID: {teacher.name}")
                except (Teacher.DoesNotExist, ValueError):
                    os.remove(file_path)  # Clean up uploaded file
                    return JsonResponse(
                        {"error": f"Teacher not found with ID: {entity_id}"}, status=404
                    )

        return JsonResponse(
            {
                "message": "Photo uploaded successfully",
                "photo_url": photo_url,
                "file_name": safe_filename,
            }
        )

    except Exception as e:
        print(f"Error in photo upload: {str(e)}")
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


# ============== USER ROLE MANAGEMENT API ==============
# ============== USER ROLE MANAGEMENT API ==============
@login_required
@require_http_methods(["GET"])
def get_current_user_role(request):
    """Get the current user's role and permissions"""
    try:
        from django.contrib.auth.models import User

        # Default permissions for each role - used as fallback
        default_permissions = {
            "chairman": {  # CHAIRMAN - Overall admin, full access to EVERYTHING
                "dashboard": True,
                "courses": True,
                "course-categories": True,
                "departments": True,
                "students": True,
                "teachers": True,
                "audit": True,
                "grades": True,
                "assigned": True,
                "reports": True,
                "library": True,
                "documents": True,
                "settings": True,  # Chairman can access settings
            },
            "teacher": {  # RECORD OFFICER
                "dashboard": True,
                "courses": False,
                "course-categories": False,
                "departments": False,
                "students": True,  # Can view students for grade entry
                "teachers": False,
                "audit": False,
                "grades": True,  # Can enter grades
                "assigned": True,  # Can view their assignments
                "reports": False,
                "library": True,  # Can access library
                "documents": True,  # Can access documents
                "settings": False,
            },
            "clearing": {  # CLEARING OFFICER
                "dashboard": True,
                "courses": False,
                "course-categories": False,
                "departments": False,
                "students": True,  # Can view students for audit
                "teachers": False,
                "audit": True,  # Can do degree audit
                "grades": False,
                "assigned": False,
                "reports": True,  # Can view reports
                "library": False,
                "documents": False,
                "settings": False,
            },
            "assistant": {  # ADMINISTRATIVE ASSISTANT
                "dashboard": True,
                "courses": True,
                "course-categories": True,
                "departments": True,
                "students": True,
                "teachers": True,
                "audit": True,
                "grades": True,
                "assigned": True,
                "reports": True,
                "library": True,
                "documents": True,
                "settings": False,  # Administrative Assistant cannot access settings
            },
        }

        # Get or create user role
        role, created = UserRole.objects.get_or_create(
            user=request.user,
            defaults={"role": "teacher", "permissions": default_permissions["teacher"]},
        )

        # If role was just created, set appropriate permissions
        if created:
            role.permissions = default_permissions.get(
                role.role, default_permissions["teacher"]
            )
            role.save()

        # IMPORTANT: Check if permissions exist and are not empty
        # If permissions are empty, use defaults, BUT DO NOT OVERWRITE EXISTING CUSTOM PERMISSIONS
        if not role.permissions or len(role.permissions) == 0:
            # Only set defaults if permissions are completely empty
            role.permissions = default_permissions.get(
                role.role, default_permissions["teacher"]
            )
            role.save()

        # Ensure all required permission keys exist (merge with defaults if missing)
        # This preserves custom permissions while ensuring new menu items have defaults
        defaults = default_permissions.get(role.role, default_permissions["teacher"])
        current_perms = role.permissions

        # Add any missing keys from defaults (preserves custom settings)
        for key, value in defaults.items():
            if key not in current_perms:
                current_perms[key] = value

        # Save only if we added missing keys
        if set(current_perms.keys()) != set(role.permissions.keys()):
            role.permissions = current_perms
            role.save()

        return JsonResponse(
            {
                "user_id": str(request.user.id),
                "username": request.user.username,
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "role": role.role,
                "role_display": role.get_role_display(),
                "permissions": role.permissions,
            }
        )
    except Exception as e:
        print(f"Error in get_current_user_role: {str(e)}")
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def get_all_user_roles(request):
    """Get all users with their roles (Chairman only)"""
    try:
        # Check if current user is chairman
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        from django.contrib.auth.models import User

        users = User.objects.filter(is_active=True).select_related("user_role")
        result = []

        for user in users:
            role_obj = getattr(user, "user_role", None)
            result.append(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": role_obj.role if role_obj else "teacher",
                    "role_display": (
                        role_obj.get_role_display() if role_obj else "Record Officer"
                    ),
                    "permissions": role_obj.permissions if role_obj else {},
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                    "date_joined": (
                        user.date_joined.isoformat() if user.date_joined else None
                    ),
                }
            )

        return JsonResponse(result, safe=False)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
@csrf_exempt
def update_user_role(request, user_id):
    """Update a user's role (admin only)"""
    try:
        # Check if current user is admin
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Admin access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        from django.contrib.auth.models import User

        data = json.loads(request.body)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        role, created = UserRole.objects.get_or_create(user=user)
        role.role = data.get("role", role.role)
        role.save()

        return JsonResponse(
            {
                "message": "User role updated successfully",
                "user_id": str(user.id),
                "username": user.username,
                "role": role.role,
                "role_display": role.get_role_display(),
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def update_role_permissions(request):
    """Update permissions for a role (Chairman only)"""
    try:
        # Check if current user is chairman
        try:
            current_role = UserRole.objects.get(user=request.user)
            if current_role.role != "chairman":
                return JsonResponse(
                    {"error": "Unauthorized - Chairman access required"}, status=403
                )
        except UserRole.DoesNotExist:
            return JsonResponse({"error": "User role not found"}, status=403)

        data = json.loads(request.body)
        role_name = data.get("role")
        permissions = data.get("permissions", {})

        # Validate role_name
        valid_roles = ["chairman", "teacher", "clearing", "assistant"]
        if role_name not in valid_roles:
            return JsonResponse(
                {
                    "error": f"Invalid role name. Must be one of: {', '.join(valid_roles)}"
                },
                status=400,
            )

        # Log the update for debugging
        print("=" * 50)
        print(f"Updating permissions for role: {role_name}")
        print(f"New permissions: {permissions}")
        print("=" * 50)

        # Get all users with this role
        users_with_role = UserRole.objects.filter(role=role_name)
        user_count = users_with_role.count()

        print(f"Found {user_count} users with role {role_name}")

        # Update each user individually to ensure save() is called
        updated_count = 0
        for user_role in users_with_role:
            user_role.permissions = permissions
            user_role.save()
            updated_count += 1
            print(f"Updated user: {user_role.user.username}")

        print(f"Successfully updated {updated_count} users with role {role_name}")

        return JsonResponse(
            {
                "message": f"Permissions updated successfully for role {role_name}",
                "role": role_name,
                "permissions": permissions,
                "users_updated": updated_count,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        print(f"Error updating permissions: {str(e)}")
        import traceback

        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)


# ============== EMAIL SENDING VIEWS ==============
# Add these before the helper functions (calculate_progress, calculate_cgpa, etc.)

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def send_custom_email_view(request):
    """
    Send custom email to any recipient with optional attachment and custom message
    Expected JSON payload:
    {
        "recipient_email": "user@gmail.com",
        "subject": "Email Subject",
        "custom_message": "Your custom message here",
        "attachment_id": "optional-document-id",
        "cc_emails": ["cc1@gmail.com", "cc2@gmail.com"]  # optional
    }
    """
    try:
        data = json.loads(request.body)
        
        recipient_email = data.get('recipient_email')
        subject = data.get('subject')
        custom_message = data.get('custom_message', '')
        attachment_id = data.get('attachment_id')
        cc_emails = data.get('cc_emails', [])
        
        # Validate required fields
        if not recipient_email:
            return JsonResponse({"error": "Recipient email is required"}, status=400)
        if not subject:
            return JsonResponse({"error": "Subject is required"}, status=400)
        
        # Get sender name from request user
        sender_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not sender_name:
            sender_name = request.user.username
        
        # Check if attachment is provided
        attachment_path = None
        attachment_name = None
        if attachment_id:
            try:
                document = DepartmentDocument.objects.get(id=attachment_id)
                if document.file and os.path.exists(document.file.path):
                    attachment_path = document.file.path
                    attachment_name = document.title
            except DepartmentDocument.DoesNotExist:
                pass  # Continue without attachment
        
        # Build HTML email with custom message
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #fff; }}
                .header {{ background: linear-gradient(135deg, #1e3a8a, #2563eb); color: white; padding: 30px 20px; text-align: center; }}
                .header h2 {{ margin: 0 0 5px 0; font-size: 24px; }}
                .header h3 {{ margin: 0; font-size: 16px; font-weight: normal; opacity: 0.9; }}
                .content {{ padding: 30px; background: #f8fafc; }}
                .message-box {{ background: white; padding: 20px; border-radius: 12px; margin: 20px 0; border-left: 4px solid #2563eb; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
                .message-box p {{ margin: 0 0 10px 0; }}
                .message-box p:last-child {{ margin-bottom: 0; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; background: #f1f5f9; border-top: 1px solid #e2e8f0; }}
                .footer p {{ margin: 5px 0; }}
                .badge {{ display: inline-block; background: #e0e7ff; color: #1e40af; padding: 4px 12px; border-radius: 20px; font-size: 12px; margin-top: 10px; }}
                .attachment-note {{ background: #fef3c7; padding: 10px 15px; border-radius: 8px; margin-top: 15px; font-size: 13px; color: #92400e; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>University of Liberia</h2>
                    <h3>Department of Political Science</h3>
                </div>
                <div class="content">
                    <p>Dear Recipient,</p>
                    <div class="message-box">
                        {custom_message.replace(chr(10), '<br>') if custom_message else '<p><em>No additional message provided.</em></p>'}
                    </div>
                    {'<div class="attachment-note"><strong>📎 Attachment:</strong> ' + attachment_name + ' is attached to this email.</div>' if attachment_name else ''}
                    <p style="margin-top: 20px;">Best regards,<br><strong>{sender_name}</strong><br>Department of Political Science</p>
                    <div class="badge">Official Communication</div>
                </div>
                <div class="footer">
                    <p>University of Liberia, Department of Political Science</p>
                    <p>Capitol Hill, Monrovia, Liberia | Tel: +231 777 123 456</p>
                    <p>This is an automated message from the Departmental System. Please do not reply directly to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version (without HTML)
        plain_message = f"""
        UNIVERSITY OF LIBERIA - DEPARTMENT OF POLITICAL SCIENCE
        {'=' * 60}
        
        Subject: {subject}
        
        Message:
        {custom_message if custom_message else 'No additional message provided.'}
        
        {'Attachment: ' + attachment_name if attachment_name else ''}
        
        Regards,
        {sender_name}
        Department of Political Science
        University of Liberia
        """
        
        # Send the email
        success, result_message = send_custom_email(
            subject=subject,
            message=plain_message,
            recipient_list=[recipient_email],
            attachment_path=attachment_path,
            attachment_name=attachment_name,
            html_message=html_content,
            cc_list=cc_emails if cc_emails else None
        )
        
        # Log the email (optional - if you have EmailLog model)
        try:
            from .models import EmailLog
            EmailLog.objects.create(
                email_type='custom',
                subject=subject,
                recipient=recipient_email,
                cc_recipients=','.join(cc_emails) if cc_emails else None,
                attachment_names=attachment_name if attachment_name else None,
                status='sent' if success else 'failed',
                error_message=result_message if not success else None,
                sent_by=request.user
            )
        except:
            pass  # EmailLog model might not exist yet
        
        if success:
            return JsonResponse({
                "success": True,
                "message": f"Email sent successfully to {recipient_email}",
                "recipient": recipient_email,
                "subject": subject
            })
        else:
            return JsonResponse({
                "success": False,
                "error": result_message
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def send_grade_email(request):
    """
    Send grade notification email to a student with custom message
    Expected JSON payload:
    {
        "student_id": "student-uuid",
        "course_id": "course-uuid", 
        "grade": "A",
        "custom_message": "Your custom message here",
        "semester": "semester1",
        "year": 2026
    }
    """
    try:
        data = json.loads(request.body)
        
        student_id = data.get('student_id')
        course_id = data.get('course_id')
        grade = data.get('grade')
        custom_message = data.get('custom_message', '')
        semester = data.get('semester', 'semester1')
        year = data.get('year', timezone.now().year)
        
        # Get student and course
        try:
            student = Student.objects.get(id=student_id)
            course = Course.objects.get(id=course_id)
        except (Student.DoesNotExist, Course.DoesNotExist) as e:
            return JsonResponse({"error": str(e)}, status=404)
        
        if not student.email:
            return JsonResponse({"error": "Student has no email address"}, status=400)
        
        semester_display = "Semester 1" if semester == "semester1" else "Semester 2"
        
        # Get sender name
        sender_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not sender_name:
            sender_name = request.user.username
        
        # Build HTML email
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .grade-box {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #2563eb; }}
                .grade {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
                .custom-message {{ background: #f0fdf4; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #10b981; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>University of Liberia</h2>
                    <h3>Department of Political Science</h3>
                </div>
                <div class="content">
                    <h3>Dear {student.name},</h3>
                    <p>Your grade for the following course has been recorded:</p>
                    <div class="grade-box">
                        <strong>Course:</strong> {course.code} - {course.title}<br>
                        <strong>Semester:</strong> {semester_display} {year}<br>
                        <strong>Grade:</strong> <span class="grade">{grade}</span>
                    </div>
                    {'<div class="custom-message"><strong>📝 Message from Department:</strong><br>' + custom_message.replace(chr(10), '<br>') + '</div>' if custom_message else ''}
                    <p>Please log in to the portal to view your complete academic record.</p>
                    <p>Best regards,<br><strong>{sender_name}</strong><br>Department of Political Science</p>
                </div>
                <div class="footer">
                    <p>University of Liberia, Department of Political Science<br>Capitol Hill, Monrovia, Liberia</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_message = f"""
        UNIVERSITY OF LIBERIA - DEPARTMENT OF POLITICAL SCIENCE
        
        Dear {student.name},
        
        Your grade for {course.code} - {course.title} has been recorded:
        
        Course: {course.code} - {course.title}
        Semester: {semester_display} {year}
        Grade: {grade}
        
        {'Message from Department: ' + custom_message if custom_message else ''}
        
        Please log in to the portal to view your complete academic record.
        
        Regards,
        {sender_name}
        Department of Political Science
        """
        
        # Try to generate and attach PDF report
        attachment_path = None
        try:
            pdf_response = export_student_pdf(request, student_id)
            if pdf_response.status_code == 200:
                temp_pdf_path = os.path.join(settings.MEDIA_ROOT, f'temp_{student.student_id}_report.pdf')
                with open(temp_pdf_path, 'wb') as f:
                    f.write(pdf_response.content)
                attachment_path = temp_pdf_path
        except:
            pass
        
        # Send email
        success, result_message = send_custom_email(
            subject=f"Grade Notification: {course.code} - {grade}",
            message=plain_message,
            recipient_list=[student.email],
            attachment_path=attachment_path,
            attachment_name=f"{student.student_id}_academic_report.pdf",
            html_message=html_content
        )
        
        # Clean up temp file
        if attachment_path and os.path.exists(attachment_path):
            os.remove(attachment_path)
        
        if success:
            return JsonResponse({
                "success": True,
                "message": f"Grade notification sent to {student.email}"
            })
        else:
            return JsonResponse({"error": result_message}, status=500)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def send_document_email(request):
    """
    Send a document via email with custom message
    Expected JSON payload:
    {
        "document_id": "document-uuid",
        "recipient_email": "user@gmail.com",
        "custom_message": "Your custom message here",
        "recipient_name": "Student Name"  # optional
    }
    """
    try:
        data = json.loads(request.body)
        
        document_id = data.get('document_id')
        recipient_email = data.get('recipient_email')
        custom_message = data.get('custom_message', '')
        recipient_name = data.get('recipient_name', 'Recipient')
        
        if not document_id:
            return JsonResponse({"error": "Document ID is required"}, status=400)
        if not recipient_email:
            return JsonResponse({"error": "Recipient email is required"}, status=400)
        
        # Get document
        try:
            document = DepartmentDocument.objects.get(id=document_id)
        except DepartmentDocument.DoesNotExist:
            return JsonResponse({"error": "Document not found"}, status=404)
        
        if not document.file or not os.path.exists(document.file.path):
            return JsonResponse({"error": "Document file not found"}, status=404)
        
        # Get sender name
        sender_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not sender_name:
            sender_name = request.user.username
        
        # Build HTML email
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .document-info {{ background: white; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .custom-message {{ background: #fef3c7; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #f59e0b; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>University of Liberia</h2>
                    <h3>Department of Political Science</h3>
                </div>
                <div class="content">
                    <h3>Dear {recipient_name},</h3>
                    <p>The following document has been shared with you:</p>
                    <div class="document-info">
                        <strong>Title:</strong> {document.title}<br>
                        <strong>Author:</strong> {document.author}<br>
                        <strong>Type:</strong> {document.document_type.upper()}<br>
                        <strong>Category:</strong> {document.category or 'General'}
                    </div>
                    {'<div class="custom-message"><strong>📝 Message from {sender_name}:</strong><br>' + custom_message.replace(chr(10), '<br>') + '</div>' if custom_message else ''}
                    <p>Please find the document attached to this email.</p>
                    <p>Best regards,<br><strong>{sender_name}</strong><br>Department of Political Science</p>
                </div>
                <div class="footer">
                    <p>University of Liberia, Department of Political Science<br>Capitol Hill, Monrovia, Liberia</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_message = f"""
        UNIVERSITY OF LIBERIA - DEPARTMENT OF POLITICAL SCIENCE
        
        Dear {recipient_name},
        
        The following document has been shared with you:
        
        Title: {document.title}
        Author: {document.author}
        Type: {document.document_type.upper()}
        Category: {document.category or 'General'}
        
        {'Message from ' + sender_name + ': ' + custom_message if custom_message else ''}
        
        Please find the document attached to this email.
        
        Regards,
        {sender_name}
        Department of Political Science
        """
        
        # Send email with document attachment
        success, result_message = send_custom_email(
            subject=f"Document Shared: {document.title}",
            message=plain_message,
            recipient_list=[recipient_email],
            attachment_path=document.file.path,
            attachment_name=f"{document.title}.{document.file.path.split('.')[-1]}",
            html_message=html_content
        )
        
        if success:
            return JsonResponse({
                "success": True,
                "message": f"Document sent to {recipient_email}"
            })
        else:
            return JsonResponse({"error": result_message}, status=500)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


# ============== HELPER FUNCTIONS ==============
def calculate_progress(student):
    """Calculate student progress"""
    required_target = 65
    major_target = 45
    minor_target = 18
    elective_target = 6

    req_credits = 0
    major_credits = 0
    minor_credits = 0
    elective_credits = 0
    total_credits = 0

    for course_id, grade in student.completed_courses.items():
        if grade in ["IP", None, "F"]:
            continue

        # Check regular courses
        try:
            course = Course.objects.get(id=course_id)
            total_credits += course.credits

            if course.course_type == "required":
                req_credits += course.credits
            elif course.course_type == "major":
                major_credits += course.credits
            elif course.course_type == "minor":
                minor_credits += course.credits
            elif course.course_type == "elective":
                elective_credits += course.credits
        except Course.DoesNotExist:
            continue

    total_required = required_target + major_target
    if student.track:  # If student has a track
        total_required += minor_target + elective_target

    completed_credits = min(req_credits, required_target) + min(
        major_credits, major_target
    )
    if student.track:
        completed_credits += min(minor_credits, minor_target) + min(
            elective_credits, elective_target
        )

    percent_complete = (
        (completed_credits / total_required * 100) if total_required > 0 else 0
    )

    return {
        "required": min(req_credits, required_target),
        "major": min(major_credits, major_target),
        "minor": min(minor_credits, minor_target) if student.track else 0,
        "electives": min(elective_credits, elective_target) if student.track else 0,
        "completed_credits": completed_credits,
        "total_required": total_required,
        "percent_complete": round(percent_complete, 1),
    }


def calculate_cgpa(student):
    """Calculate CGPA based on completed courses"""
    grade_points = {
        "A": 4.0,
        "A-": 3.7,
        "B+": 3.3,
        "B": 3.0,
        "B-": 2.7,
        "C+": 2.3,
        "C": 2.0,
        "D": 1.0,
        "F": 0.0,
    }

    total_points = 0
    total_credits = 0

    for course_id, grade in student.completed_courses.items():
        if grade not in grade_points:
            continue

        # Try regular course
        try:
            course = Course.objects.get(id=course_id)
            total_points += grade_points[grade] * course.credits
            total_credits += course.credits
        except Course.DoesNotExist:
            continue

    return round(total_points / total_credits, 2) if total_credits > 0 else 0.0


def calculate_honors(cgpa):
    """Determine honors status"""
    if cgpa >= 3.9:
        return {"level": "Summa Cum Laude", "range": "3.90-4.00"}
    elif cgpa >= 3.7:
        return {"level": "Magna Cum Laude", "range": "3.70-3.89"}
    elif cgpa >= 3.5:
        return {"level": "Cum Laude", "range": "3.50-3.69"}
    elif cgpa >= 2.0:
        return {"level": "Pass", "range": "2.00-3.49"}
    else:
        return {"level": "Not Eligible", "range": "Below 2.00"}


def get_class_standing(student):
    """Determine class standing based on course completion percentage"""
    progress = calculate_progress(student)
    percent_complete = progress["percent_complete"]

    if percent_complete <= 25:
        return "Freshman"
    elif percent_complete <= 50:
        return "Sophomore"
    elif percent_complete <= 75:
        return "Junior"
    else:
        return "Senior"
