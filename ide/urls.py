"""
IDE URL Configuration
"""

from django.urls import path
from . import views

app_name = "ide"

urlpatterns = [
    # Page routes
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("editor/<uuid:project_id>/", views.editor, name="editor"),
    
    # Project API
    path("api/projects/create/", views.create_project, name="create_project"),
    path("api/projects/<uuid:project_id>/delete/", views.delete_project, name="delete_project"),
    path("api/projects/<uuid:project_id>/index/", views.index_project, name="index_project"),
    
    # File System API
    path("api/projects/<uuid:project_id>/files/tree/", views.get_file_tree, name="get_file_tree"),
    path("api/projects/<uuid:project_id>/files/content/", views.get_file_content, name="get_file_content"),
    path("api/projects/<uuid:project_id>/files/save/", views.save_file, name="save_file"),
    path("api/projects/<uuid:project_id>/files/create/", views.create_file, name="create_file"),
    path("api/projects/<uuid:project_id>/files/run/", views.run_file, name="run_file"),
    
    # Agent Chat API
    path("api/projects/<uuid:project_id>/chat/", views.chat, name="chat"),
    
    # Change Management API
    path("api/projects/<uuid:project_id>/changes/<uuid:change_id>/apply/", views.apply_change, name="apply_change"),
    path("api/projects/<uuid:project_id>/changes/<uuid:change_id>/reject/", views.reject_change, name="reject_change"),
    path("api/projects/<uuid:project_id>/changes/<uuid:change_id>/preview/", views.preview_change, name="preview_change"),
]
