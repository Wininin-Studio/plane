# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import transaction
from django.db.models import Prefetch, Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import (
    PageAPISerializer,
    PageCreateAPISerializer,
    PageUpdateAPISerializer,
    WorkItemPageAPISerializer,
    WorkItemPageCreateAPISerializer,
)
from plane.app.permissions import ProjectEntityPermission, WorkspaceEntityPermission
from plane.bgtasks.page_transaction_task import page_transaction
from plane.db.models import Issue, Page, PageLog, Project, ProjectPage, Workspace
from plane.utils.openapi import (
    CURSOR_PARAMETER,
    INVALID_REQUEST_RESPONSE,
    PER_PAGE_PARAMETER,
    create_paginated_response,
)

from .base import BaseAPIView


def visible_project_pages_prefetch(user):
    return Prefetch(
        "project_pages",
        queryset=ProjectPage.objects.filter(
            project__project_projectmember__member=user,
            project__project_projectmember__is_active=True,
            project__project_projectmember__deleted_at__isnull=True,
        ).only("page_id", "project_id"),
        to_attr="visible_project_pages",
    )


def update_page_response(request, page):
    if page.is_locked:
        return Response(
            {"error": "Page is locked"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    old_description_html = page.description_html
    serializer = PageUpdateAPISerializer(
        page,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    if (
        "access" in serializer.validated_data
        and serializer.validated_data["access"] != page.access
        and page.owned_by_id != request.user.id
    ):
        return Response(
            {"error": "Only the page owner can change page access"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    page = serializer.save(updated_by=request.user)
    if "description_html" in serializer.validated_data:
        new_description_html = page.description_html
        page_id = page.id
        transaction.on_commit(
            lambda: page_transaction.delay(
                new_description_html=new_description_html,
                old_description_html=old_description_html,
                page_id=page_id,
            )
        )
    return Response(
        PageAPISerializer(page, context={"request": request}).data,
        status=status.HTTP_200_OK,
    )


class WorkspacePageListAPIEndpoint(BaseAPIView):
    serializer_class = PageAPISerializer
    permission_classes = [WorkspaceEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="list_workspace_pages",
        summary="List workspace pages",
        parameters=[CURSOR_PARAMETER, PER_PAGE_PARAMETER],
        responses={
            200: create_paginated_response(
                PageAPISerializer,
                "PaginatedWorkspacePageResponse",
                "Paginated list of workspace pages",
                "Workspace pages",
            )
        },
    )
    def get(self, request, slug):
        pages = (
            Page.objects.filter(workspace__slug=slug, is_global=True)
            .filter(Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user))
            .prefetch_related(visible_project_pages_prefetch(request.user))
            .distinct()
            .order_by("-created_at")
        )
        return self.paginate(
            request=request,
            queryset=pages,
            on_results=lambda results: PageAPISerializer(
                results,
                many=True,
                context={"request": request},
            ).data,
        )

    @extend_schema(
        tags=["Pages"],
        operation_id="create_workspace_page",
        summary="Create a workspace page",
        request=PageCreateAPISerializer,
        responses={201: PageAPISerializer, 400: INVALID_REQUEST_RESPONSE},
    )
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        serializer = PageCreateAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save(
            workspace=workspace,
            owned_by=request.user,
            created_by=request.user,
            updated_by=request.user,
            is_global=True,
        )
        transaction.on_commit(
            lambda: page_transaction.delay(
                new_description_html=page.description_html,
                old_description_html=None,
                page_id=page.id,
            )
        )
        return Response(
            PageAPISerializer(page, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class WorkspacePageDetailAPIEndpoint(BaseAPIView):
    serializer_class = PageAPISerializer
    permission_classes = [WorkspaceEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="retrieve_workspace_page",
        summary="Retrieve a workspace page",
        responses={200: PageAPISerializer},
    )
    def get(self, request, slug, page_id):
        page = Page.objects.get(
            Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user),
            id=page_id,
            workspace__slug=slug,
            is_global=True,
        )
        return Response(
            PageAPISerializer(page, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Pages"],
        operation_id="update_workspace_page",
        summary="Update a workspace page",
        request=PageUpdateAPISerializer,
        responses={
            200: PageAPISerializer,
            400: INVALID_REQUEST_RESPONSE,
        },
    )
    @transaction.atomic
    def patch(self, request, slug, page_id):
        page = Page.objects.select_for_update().get(
            Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user),
            id=page_id,
            workspace__slug=slug,
            is_global=True,
        )
        return update_page_response(request, page)


class ProjectPageListAPIEndpoint(BaseAPIView):
    serializer_class = PageAPISerializer
    permission_classes = [ProjectEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="list_project_pages",
        summary="List project pages",
        parameters=[CURSOR_PARAMETER, PER_PAGE_PARAMETER],
        responses={
            200: create_paginated_response(
                PageAPISerializer,
                "PaginatedProjectPageResponse",
                "Paginated list of project pages",
                "Project pages",
            )
        },
    )
    def get(self, request, slug, project_id):
        pages = (
            Page.objects.filter(
                workspace__slug=slug,
                project_pages__project_id=project_id,
                project_pages__deleted_at__isnull=True,
            )
            .filter(Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user))
            .prefetch_related(visible_project_pages_prefetch(request.user))
            .distinct()
            .order_by("-created_at")
        )
        return self.paginate(
            request=request,
            queryset=pages,
            on_results=lambda results: PageAPISerializer(
                results,
                many=True,
                context={"request": request},
            ).data,
        )

    @extend_schema(
        tags=["Pages"],
        operation_id="create_project_page",
        summary="Create a project page",
        request=PageCreateAPISerializer,
        responses={201: PageAPISerializer, 400: INVALID_REQUEST_RESPONSE},
    )
    @transaction.atomic
    def post(self, request, slug, project_id):
        project = Project.objects.get(id=project_id, workspace__slug=slug)
        serializer = PageCreateAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save(
            workspace=project.workspace,
            owned_by=request.user,
            created_by=request.user,
            updated_by=request.user,
            is_global=False,
        )
        ProjectPage.objects.create(
            workspace=project.workspace,
            project=project,
            page=page,
            created_by=request.user,
            updated_by=request.user,
        )
        transaction.on_commit(
            lambda: page_transaction.delay(
                new_description_html=page.description_html,
                old_description_html=None,
                page_id=page.id,
            )
        )
        return Response(
            PageAPISerializer(page, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectPageDetailAPIEndpoint(BaseAPIView):
    serializer_class = PageAPISerializer
    permission_classes = [ProjectEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="retrieve_project_page",
        summary="Retrieve a project page",
        responses={200: PageAPISerializer},
    )
    def get(self, request, slug, project_id, page_id):
        page = Page.objects.get(
            Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user),
            id=page_id,
            workspace__slug=slug,
            project_pages__project_id=project_id,
            project_pages__deleted_at__isnull=True,
        )
        return Response(
            PageAPISerializer(page, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Pages"],
        operation_id="update_project_page",
        summary="Update a project page",
        request=PageUpdateAPISerializer,
        responses={
            200: PageAPISerializer,
            400: INVALID_REQUEST_RESPONSE,
        },
    )
    @transaction.atomic
    def patch(self, request, slug, project_id, page_id):
        page = Page.objects.select_for_update().get(
            Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user),
            id=page_id,
            workspace__slug=slug,
            project_pages__project_id=project_id,
            project_pages__deleted_at__isnull=True,
        )
        return update_page_response(request, page)


class WorkItemPageListCreateAPIEndpoint(BaseAPIView):
    serializer_class = WorkItemPageAPISerializer
    permission_classes = [ProjectEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="list_work_item_pages",
        summary="List pages attached to a work item",
        parameters=[CURSOR_PARAMETER, PER_PAGE_PARAMETER],
        responses={
            200: create_paginated_response(
                WorkItemPageAPISerializer,
                "PaginatedWorkItemPageResponse",
                "Paginated list of pages attached to a work item",
                "Work item pages",
            )
        },
    )
    def get(self, request, slug, project_id, work_item_id):
        Issue.objects.get(
            id=work_item_id,
            workspace__slug=slug,
            project_id=project_id,
        )
        page_links = (
            PageLog.objects.filter(
                workspace__slug=slug,
                entity_name="issue",
                entity_type="issue",
                entity_identifier=work_item_id,
            )
            .filter(
                Q(page__is_global=True)
                | Q(
                    page__project_pages__project_id=project_id,
                    page__project_pages__deleted_at__isnull=True,
                )
            )
            .filter(Q(page__access=Page.PUBLIC_ACCESS) | Q(page__owned_by=request.user))
            .select_related("page")
            .distinct()
            .order_by("-created_at")
        )
        return self.paginate(
            request=request,
            queryset=page_links,
            on_results=lambda results: WorkItemPageAPISerializer(
                results,
                many=True,
                context={"project_id": project_id},
            ).data,
        )

    @extend_schema(
        tags=["Pages"],
        operation_id="attach_page_to_work_item",
        summary="Attach a page to a work item",
        request=WorkItemPageCreateAPISerializer,
        responses={
            200: WorkItemPageAPISerializer,
            201: WorkItemPageAPISerializer,
            400: INVALID_REQUEST_RESPONSE,
        },
    )
    @transaction.atomic
    def post(self, request, slug, project_id, work_item_id):
        work_item = Issue.objects.get(
            id=work_item_id,
            workspace__slug=slug,
            project_id=project_id,
        )
        serializer = WorkItemPageCreateAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = Page.objects.select_for_update().get(
            Q(access=Page.PUBLIC_ACCESS) | Q(owned_by=request.user),
            id=serializer.validated_data["page_id"],
            workspace__slug=slug,
        )
        if (
            not page.is_global
            and not ProjectPage.objects.filter(
                page=page,
                project_id=project_id,
            ).exists()
        ):
            raise Page.DoesNotExist
        page_log = (
            PageLog.objects.filter(
                page=page,
                entity_name="issue",
                entity_type="issue",
                entity_identifier=work_item.id,
                workspace=work_item.workspace,
            )
            .order_by("created_at")
            .first()
        )
        created = page_log is None
        if page_log is None:
            page_log = PageLog.objects.create(
                page=page,
                entity_name="issue",
                entity_type="issue",
                entity_identifier=work_item.id,
                workspace=work_item.workspace,
                created_by=request.user,
                updated_by=request.user,
            )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            WorkItemPageAPISerializer(page_log, context={"project_id": project_id}).data,
            status=response_status,
        )


class WorkItemPageDetailAPIEndpoint(BaseAPIView):
    serializer_class = WorkItemPageAPISerializer
    permission_classes = [ProjectEntityPermission]

    @extend_schema(
        tags=["Pages"],
        operation_id="detach_page_from_work_item",
        summary="Detach a page from a work item",
        responses={204: OpenApiResponse(description="Page detached from work item")},
    )
    def delete(
        self,
        request,
        slug,
        project_id,
        work_item_id,
        work_item_page_id,
    ):
        Issue.objects.get(
            id=work_item_id,
            workspace__slug=slug,
            project_id=project_id,
        )
        page_link = PageLog.objects.get(
            Q(page__is_global=True)
            | Q(
                page__project_pages__project_id=project_id,
                page__project_pages__deleted_at__isnull=True,
            ),
            Q(page__access=Page.PUBLIC_ACCESS) | Q(page__owned_by=request.user),
            id=work_item_page_id,
            workspace__slug=slug,
            entity_name="issue",
            entity_type="issue",
            entity_identifier=work_item_id,
        )
        page_link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
