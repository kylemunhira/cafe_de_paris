from accounts.branch_access import user_can_manage_currencies
from audit.mixins import AuditedModelMixin
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Currency, CurrencyRate
from .serializers import CurrencyRateSerializer, CurrencySerializer


class CurrencyViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    audit_entity_type = "currency"
    audit_fields = ("code", "name", "symbol", "is_base", "is_active")
    audit_label_field = "name"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not user_can_manage_currencies(request.user):
                raise PermissionDenied("You do not have permission to manage currencies.")


class CurrencyRateViewSet(AuditedModelMixin, viewsets.ModelViewSet):
    queryset = CurrencyRate.objects.select_related("currency").all()
    serializer_class = CurrencyRateSerializer
    audit_entity_type = "currency_rate"
    audit_fields = ("currency", "rate", "effective_from", "is_active")
    audit_label_field = lambda rate: (  # noqa: E731
        f"{rate.currency_id} @ {rate.rate}"
    )
