# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import (
    ProjectFeatureSerializer,
    ProjectFeatureUpdateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
    WorkspaceFeatureSerializer,
    WorkspaceFeatureUpdateSerializer,
)
from plane.app.permissions import ProjectBasePermission, ProjectEntityPermission, WorkspaceEntityPermission
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import Intake, Project
from plane.utils.host import base_host

from .base import BaseAPIView


class WorkspaceFeatureAPIEndpoint(BaseAPIView):
    serializer_class = WorkspaceFeatureSerializer
    permission_classes = [WorkspaceEntityPermission]

    @extend_schema(
        tags=["Features"],
        operation_id="get_workspace_features",
        summary="Get workspace features",
        responses={200: WorkspaceFeatureSerializer},
    )
    def get(self, request, slug):
        return Response(WorkspaceFeatureSerializer(self.features).data, status=status.HTTP_200_OK)

    @property
    def features(self):
        return {
            "project_grouping": False,
            "initiatives": False,
            "teams": False,
            "customers": False,
            "wiki": False,
            "pi": False,
        }

    @extend_schema(
        tags=["Features"],
        operation_id="update_workspace_features",
        summary="Update workspace features",
        request=WorkspaceFeatureUpdateSerializer,
        responses={200: WorkspaceFeatureSerializer},
    )
    def patch(self, request, slug):
        serializer = WorkspaceFeatureUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(WorkspaceFeatureSerializer(self.features).data, status=status.HTTP_200_OK)


class ProjectFeatureAPIEndpoint(BaseAPIView):
    serializer_class = ProjectFeatureSerializer
    permission_classes = [ProjectEntityPermission]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [ProjectBasePermission()]
        return super().get_permissions()

    def get_project(self, slug, project_id):
        return Project.objects.get(id=project_id, workspace__slug=slug)

    @extend_schema(
        tags=["Features"],
        operation_id="get_project_features",
        summary="Get project features",
        responses={200: ProjectFeatureSerializer},
    )
    def get(self, request, slug, project_id):
        project = self.get_project(slug, project_id)
        return Response(ProjectFeatureSerializer(project).data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Features"],
        operation_id="update_project_features",
        summary="Update project features",
        request=ProjectFeatureUpdateSerializer,
        responses={200: ProjectFeatureSerializer},
    )
    def patch(self, request, slug, project_id):
        serializer = ProjectFeatureUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = self.get_project(slug, project_id)
        if project.archived_at:
            return Response(
                {"error": "Archived project cannot be updated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        field_map = {
            "modules": "module_view",
            "cycles": "cycle_view",
            "views": "issue_views_view",
            "pages": "page_view",
            "intakes": "intake_view",
            "work_item_types": "is_issue_type_enabled",
        }
        project_data = {
            model_field: serializer.validated_data[feature]
            for feature, model_field in field_map.items()
            if feature in serializer.validated_data
        }
        if not project_data:
            return Response(ProjectFeatureSerializer(project).data, status=status.HTTP_200_OK)

        current_instance = json.dumps(ProjectSerializer(project).data, cls=DjangoJSONEncoder)

        with transaction.atomic():
            project_serializer = ProjectUpdateSerializer(
                project,
                data=project_data,
                context={"workspace_id": project.workspace_id},
                partial=True,
            )
            project_serializer.is_valid(raise_exception=True)
            project = project_serializer.save()
            if project_data.get("intake_view"):
                Intake.objects.get_or_create(
                    project=project,
                    is_default=True,
                    defaults={"name": f"{project.name} Intake"},
                )

        model_activity.delay(
            model_name="project",
            model_id=str(project.id),
            requested_data=project_data,
            current_instance=current_instance,
            actor_id=request.user.id,
            slug=slug,
            origin=base_host(request=request, is_app=True),
        )
        return Response(ProjectFeatureSerializer(project).data, status=status.HTTP_200_OK)
