from rest_framework import viewsets

from .models import Currency, CurrencyRate
from .serializers import CurrencyRateSerializer, CurrencySerializer


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer


class CurrencyRateViewSet(viewsets.ModelViewSet):
    queryset = CurrencyRate.objects.select_related("currency").all()
    serializer_class = CurrencyRateSerializer
