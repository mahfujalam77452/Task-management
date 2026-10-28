from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health),
    path("tasks/", views.tasks),
    path("tasks/sample/", views.sample_tasks),
    path("tasks/bulk/", views.bulk_tasks),
    path("tasks/bulk/preview/", views.bulk_preview),
    path("tasks/<uuid:task_id>/status/", views.task_status),
    path("tasks/<uuid:task_id>/", views.task_detail),
    path("chat/messages/", views.chat_messages),
    path("chat/prompts/<uuid:prompt_id>/answer/", views.prompt_answer),
]
