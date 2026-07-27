# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views import (
    ProjectPageDetailAPIEndpoint,
    ProjectPageListAPIEndpoint,
    WorkspacePageDetailAPIEndpoint,
    WorkspacePageListAPIEndpoint,
    WorkItemPageDetailAPIEndpoint,
    WorkItemPageListCreateAPIEndpoint,
)


urlpatterns = [
    path(
        "workspaces/<str:slug>/pages/",
        WorkspacePageListAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="workspace-pages",
    ),
    path(
        "workspaces/<str:slug>/pages/<uuid:page_id>/",
        WorkspacePageDetailAPIEndpoint.as_view(http_method_names=["get", "patch"]),
        name="workspace-page-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/pages/",
        ProjectPageListAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="project-pages",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/pages/<uuid:page_id>/",
        ProjectPageDetailAPIEndpoint.as_view(http_method_names=["get", "patch"]),
        name="project-page-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:work_item_id>/pages/",
        WorkItemPageListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="work-item-pages",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:work_item_id>/pages/<uuid:work_item_page_id>/",
        WorkItemPageDetailAPIEndpoint.as_view(http_method_names=["delete"]),
        name="work-item-page-detail",
    ),
]
