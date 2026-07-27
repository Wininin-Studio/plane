# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from plane.db.models import Page, PageLog, ProjectPage
from plane.utils.content_validator import validate_html_content

from .base import BaseSerializer


class PageAPISerializer(BaseSerializer):
    description = serializers.JSONField(source="description_json", read_only=True)
    description_binary = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "id",
            "name",
            "description",
            "description_stripped",
            "description_html",
            "description_binary",
            "access",
            "color",
            "is_locked",
            "archived_at",
            "view_props",
            "logo_props",
            "external_id",
            "external_source",
            "created_at",
            "updated_at",
            "owned_by",
            "workspace",
            "projects",
        ]
        read_only_fields = fields

    @extend_schema_field({"type": "string", "format": "byte", "nullable": True})
    def get_description_binary(self, obj) -> str | None:
        if obj.description_binary is None:
            return None
        return base64.b64encode(bytes(obj.description_binary)).decode("ascii")

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField(), read_only=True))
    def get_projects(self, obj) -> list[str]:
        visible_project_pages = getattr(obj, "visible_project_pages", None)
        if visible_project_pages is not None:
            return [str(project_page.project_id) for project_page in visible_project_pages]

        project_pages = ProjectPage.objects.filter(page=obj)
        request = self.context.get("request")
        if request is not None:
            project_pages = project_pages.filter(
                project__project_projectmember__member=request.user,
                project__project_projectmember__is_active=True,
                project__project_projectmember__deleted_at__isnull=True,
            )
        return [str(project_id) for project_id in project_pages.values_list("project_id", flat=True)]


class PageCreateAPISerializer(BaseSerializer):
    description_html = serializers.CharField(required=True, allow_blank=True)

    class Meta:
        model = Page
        fields = [
            "name",
            "description_html",
            "access",
            "color",
            "is_locked",
            "archived_at",
            "view_props",
            "logo_props",
            "external_id",
            "external_source",
        ]

    def validate_description_html(self, value):
        is_valid, error_message, sanitized_html = validate_html_content(value)
        if not is_valid:
            raise serializers.ValidationError(error_message)
        return sanitized_html if sanitized_html is not None else value


class PageUpdateAPISerializer(PageCreateAPISerializer):
    description_html = serializers.CharField(required=False, allow_blank=True)

    class Meta(PageCreateAPISerializer.Meta):
        fields = [
            "name",
            "description_html",
            "access",
            "color",
            "archived_at",
            "view_props",
            "logo_props",
            "external_id",
            "external_source",
        ]


class WorkItemPageCreateAPISerializer(serializers.Serializer):
    page_id = serializers.UUIDField()


class WorkItemPageLiteAPISerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    created_by = serializers.UUIDField(source="created_by_id", read_only=True, allow_null=True)
    is_global = serializers.BooleanField(read_only=True)
    logo_props = serializers.JSONField(read_only=True)


class WorkItemPageAPISerializer(BaseSerializer):
    page = WorkItemPageLiteAPISerializer(read_only=True)
    issue = serializers.UUIDField(source="entity_identifier", read_only=True)
    project = serializers.SerializerMethodField()

    class Meta:
        model = PageLog
        fields = [
            "id",
            "page",
            "issue",
            "project",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.UUIDField())
    def get_project(self, obj) -> str:
        return str(self.context["project_id"])
