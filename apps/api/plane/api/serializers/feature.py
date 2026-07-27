# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from plane.db.models import Project


class WorkspaceFeatureSerializer(serializers.Serializer):
    project_grouping = serializers.BooleanField(read_only=True)
    initiatives = serializers.BooleanField(read_only=True)
    teams = serializers.BooleanField(read_only=True)
    customers = serializers.BooleanField(read_only=True)
    wiki = serializers.BooleanField(read_only=True)
    pi = serializers.BooleanField(read_only=True)


class WorkspaceFeatureUpdateSerializer(serializers.Serializer):
    project_grouping = serializers.BooleanField(required=False)
    initiatives = serializers.BooleanField(required=False)
    teams = serializers.BooleanField(required=False)
    customers = serializers.BooleanField(required=False)
    wiki = serializers.BooleanField(required=False)
    pi = serializers.BooleanField(required=False)

    def validate(self, attrs):
        enabled_features = [feature for feature, enabled in attrs.items() if enabled]
        if enabled_features:
            raise serializers.ValidationError(
                {feature: "This feature is not available in Plane v1.3.1." for feature in enabled_features}
            )
        return attrs


class ProjectFeatureSerializer(serializers.ModelSerializer):
    epics = serializers.SerializerMethodField()
    modules = serializers.BooleanField(source="module_view", read_only=True)
    cycles = serializers.BooleanField(source="cycle_view", read_only=True)
    views = serializers.BooleanField(source="issue_views_view", read_only=True)
    pages = serializers.BooleanField(source="page_view", read_only=True)
    intakes = serializers.BooleanField(source="intake_view", read_only=True)
    work_item_types = serializers.BooleanField(source="is_issue_type_enabled", read_only=True)
    workflows = serializers.SerializerMethodField()
    parallel_cycles = serializers.SerializerMethodField()
    project_updates = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "epics",
            "modules",
            "cycles",
            "views",
            "pages",
            "intakes",
            "work_item_types",
            "workflows",
            "parallel_cycles",
            "project_updates",
        ]

    @extend_schema_field(serializers.BooleanField)
    def get_epics(self, obj) -> bool:
        return False

    @extend_schema_field(serializers.BooleanField)
    def get_workflows(self, obj) -> bool:
        return False

    @extend_schema_field(serializers.BooleanField)
    def get_parallel_cycles(self, obj) -> bool:
        return False

    @extend_schema_field(serializers.BooleanField)
    def get_project_updates(self, obj) -> bool:
        return False


class ProjectFeatureUpdateSerializer(serializers.Serializer):
    epics = serializers.BooleanField(required=False)
    modules = serializers.BooleanField(required=False)
    cycles = serializers.BooleanField(required=False)
    views = serializers.BooleanField(required=False)
    pages = serializers.BooleanField(required=False)
    intakes = serializers.BooleanField(required=False)
    work_item_types = serializers.BooleanField(required=False)
    workflows = serializers.BooleanField(required=False)
    parallel_cycles = serializers.BooleanField(required=False)
    project_updates = serializers.BooleanField(required=False)

    def validate(self, attrs):
        unavailable_features = (
            "epics",
            "workflows",
            "parallel_cycles",
            "project_updates",
        )
        enabled_unavailable_features = [feature for feature in unavailable_features if attrs.get(feature)]
        if enabled_unavailable_features:
            raise serializers.ValidationError(
                {feature: "This feature is not available in Plane v1.3.1." for feature in enabled_unavailable_features}
            )
        return attrs
