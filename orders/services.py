from django.utils import timezone

from .models import BranchReceiptSequence


class ReceiptNumberError(Exception):
    pass


def allocate_receipt_number(branch) -> str:
    code = (branch.code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ReceiptNumberError(
            f'Branch "{branch.name}" needs a 3-letter receipt code (e.g. HIG, CHU).'
        )

    today = timezone.localdate()
    state, _ = BranchReceiptSequence.objects.select_for_update().get_or_create(
        branch=branch
    )
    if state.sequence_date != today:
        state.sequence_date = today
        state.daily_count = 0
    state.daily_count += 1
    state.save(update_fields=["sequence_date", "daily_count"])

    date_part = today.strftime("%d%m%y")
    return f"{code}{date_part}{state.daily_count}"
