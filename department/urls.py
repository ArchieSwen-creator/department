from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # Main view
    path("", views.admin_dashboard, name="dashboard"),
    # Login/Logout
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # ============== PASSWORD MANAGEMENT ==============
    path("api/change-password/", views.change_own_password, name="change_own_password"),
    path("api/users/", views.get_all_users_for_chairman, name="get_all_users"),
    path(
        "api/users/<uuid:user_id>/",
        views.get_user_details_for_chairman,
        name="user_details",
    ),
    path(
        "api/reset-password/",
        views.reset_user_password_by_chairman,
        name="reset_password",
    ),
    # System Settings API
    path("api/settings/", views.system_settings_list, name="system_settings_list"),
    path("api/upload-logo/", views.upload_logo, name="upload_logo"),
    # Signature and logo upload endpoints
    path("api/upload-signature/", views.upload_signature, name="upload_signature"),
    path(
        "api/settings/signature/",
        views.save_signature_settings,
        name="save_signature_settings",
    ),
    # Department API
    path("api/departments/", views.department_list, name="department_list"),
    path(
        "api/departments/<uuid:pk>/", views.department_detail, name="department_detail"
    ),
    # Course Category API
    path(
        "api/course-categories/",
        views.course_category_list,
        name="course_category_list",
    ),
    path(
        "api/course-categories/<uuid:pk>/",
        views.course_category_detail,
        name="course_category_detail",
    ),
    # Dashboard API
    path("api/dashboard/", views.get_dashboard_data, name="api_dashboard"),
    # Course API
    path("api/courses/", views.course_list, name="course_list"),
    path("api/courses/<uuid:pk>/", views.course_detail, name="course_detail"),
    # Student API
    path("api/students/", views.student_list, name="student_list"),
    path("api/students/<uuid:pk>/", views.student_detail, name="student_detail"),
    # Teacher API
    path("api/teachers/", views.teacher_list, name="teacher_list"),
    path("api/teachers/<uuid:pk>/", views.teacher_detail, name="teacher_detail"),
    # Teacher Assignment API
    path("api/assignments/", views.assignment_list, name="assignment_list"),
    path(
        "api/assignments/<str:teacher_id>/",
        views.assignment_detail,
        name="assignment_detail",
    ),
    # Grade Entry API
    path("api/grades/", views.grade_entry, name="grade_entry"),
    path("api/grades/bulk/", views.bulk_grade_entry, name="bulk_grade_entry"),
    path("api/grades/records/", views.get_grade_records, name="get_grade_records"),
    path("api/grades/semester-stats/", views.get_semester_stats, name="semester_stats"),
    path("api/grades/filters/", views.get_semester_filters, name="grade_filters"),
    # PDF Export Reports
    path(
        "api/export/student/<uuid:student_id>/pdf/",
        views.export_student_pdf,
        name="export_student_pdf",
    ),
    path(
        "api/export/students/pdf/",
        views.export_all_students_pdf,
        name="export_all_students_pdf",
    ),
    path(
        "api/export/courses/pdf/", views.export_courses_pdf, name="export_courses_pdf"
    ),
    path(
        "api/export/graduates/pdf/",
        views.export_graduates_pdf,
        name="export_graduates_pdf",
    ),
    # Library API (Enhanced with CRUD)
    path("api/library/", views.library_list, name="library_list"),
    path("api/library/<uuid:pk>/", views.library_detail, name="library_detail"),
    path("api/upload-pdf/", views.upload_pdf, name="upload_pdf"),
    path("api/view-pdf/<uuid:book_id>/", views.view_pdf, name="view_pdf"),
    path("api/download-pdf/<uuid:book_id>/", views.download_pdf, name="download_pdf"),
    # Document Management API (Enhanced with CRUD)
    path("api/documents/", views.document_list, name="document_list"),
    path("api/documents/<uuid:pk>/", views.document_detail, name="document_detail"),
    path("api/upload-document/", views.upload_document_file, name="upload_document"),
    path(
        "api/view-document/<uuid:document_id>/",
        views.view_document,
        name="view_document",
    ),
    path(
        "api/download-document/<uuid:document_id>/",
        views.download_document,
        name="download_document",
    ),
    # Profile Photo Upload
    path("api/upload-photo/", views.upload_profile_photo, name="upload_profile_photo"),
    # Analytics
    path("api/analytics/", views.get_enhanced_analytics, name="enhanced_analytics"),
    path(
        "api/analytics/enhanced/",
        views.get_enhanced_analytics,
        name="enhanced_analytics_alt",
    ),
    path("api/analytics/original/", views.get_analytics, name="analytics"),
    # Enhanced Student Report
    path(
        "api/student-report/<uuid:student_id>/",
        views.enhanced_student_report,
        name="enhanced_student_report",
    ),
    # Notifications
    path("api/notifications/", views.get_notifications, name="notifications"),
    path(
        "api/notifications/mark-read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    # Export JSON
    path(
        "api/export/student/<uuid:student_id>/json/",
        views.export_student_report_json,
        name="export_student_report_json",
    ),
    # Search/Utility
    path("api/search/courses/", views.search_courses, name="search_courses"),
    path(
        "api/students/<uuid:student_id>/progress/",
        views.get_student_progress,
        name="student_progress",
    ),
    # Department Course Assignment
    path(
        "api/departments/<uuid:dept_id>/courses/",
        views.department_courses,
        name="department_courses",
    ),
    path(
        "api/departments/<uuid:dept_id>/assign-courses/",
        views.assign_department_courses,
        name="assign_department_courses",
    ),
    # Demographic Data Endpoints
    path("api/countries/", views.get_countries, name="countries"),
    path("api/counties/", views.get_liberia_counties, name="liberia_counties"),
    path("api/program-types/", views.get_program_types, name="program_types"),
    path("api/genders/", views.get_gender_options, name="genders"),
    path("api/religions/", views.get_religion_options, name="religions"),
    
    # Add these with your other URL patterns
    path('api/email/send-custom/', views.send_custom_email_view, name='send_custom_email'),
    path('api/email/send-grade/', views.send_grade_email, name='send_grade_email'),
    path('api/email/send-document/', views.send_document_email, name='send_document_email'),
    
    # ============== USER ROLE MANAGEMENT API ==============
    path("api/user/role/", views.get_current_user_role, name="current_user_role"),
    path("api/user/roles/", views.get_all_user_roles, name="all_user_roles"),
    path(
        "api/user/roles/<uuid:user_id>/",
        views.update_user_role,
        name="update_user_role",
    ),
    path(
        "api/user/roles/permissions/",
        views.update_role_permissions,
        name="update_role_permissions",
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
