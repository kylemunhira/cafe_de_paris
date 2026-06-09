from accounts.branch_access import user_can_manage_branches
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Branch
from .serializers import BranchSerializer


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not user_can_manage_branches(request.user):
                raise PermissionDenied("You do not have permission to manage branches.")
