"""
Permissions for the Document Management API.

Anonymous users cannot upload or otherwise interact with documents.
`IsDocumentOwnerOrReadOnlyForStaff` is the role-ready extension point:
today it only distinguishes "owner" vs "not owner", but future sprints
that introduce roles (e.g. "reviewer", "admin") can extend it without
changing the views that already depend on it.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAuthenticatedForDocumentAccess(BasePermission):
    """
    Base permission for all document endpoints: the platform has no
    concept of anonymous document access. Authenticated users only.
    """

    message = "Authentication is required to access documents."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsDocumentOwnerOrReadOnlyForStaff(IsAuthenticatedForDocumentAccess):
    """
    Object-level permission: a document may be freely read/modified by
    its uploader. Staff users may read any document but not modify or
    delete documents they do not own.

    This is the seam future role-based access control (e.g. an
    "analyst" role that can read all documents, or an "admin" role that
    can delete any document) should extend, rather than views
    reimplementing ownership checks themselves.
    """

    def has_object_permission(self, request, view, obj):
        if obj.uploaded_by_id == request.user.pk:
            return True

        if request.user.is_staff and request.method in SAFE_METHODS:
            return True

        return False
