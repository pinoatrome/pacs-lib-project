"""Valid pacs documents for tests: each function builds one with the library and checks
it against ISO 20022's schema (`validate`) before returning it, so a test that feeds
the system under test a pacs document can't be feeding it an invalid one.

Everything has a default, so `status_report_xml(original_message_id="PSP-0001")` is a
complete, valid pacs.002; pass what the test is about. Ids default to `TEST-...`.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from .models import Party
from .pacs002 import REJECTED, SETTLED, PaymentStatusReport, TransactionStatus, build_pacs002
from .pacs004 import PaymentReturn, ReturnedTransaction, build_pacs004
from .pacs008 import CreditTransfer, CustomerCreditTransfer, build_pacs008
from .pacs028 import StatusRequest, build_pacs028
from .validation import validate

CREATED = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


# A digital euro account number (rulebook v0.9, FUR.07): `EU`, two check digits and the 14-digit BEAN.
DEAN = re.compile(r"^EU\d{16}$")


def _party(account: str) -> Party:
    """An IBAN (starting with two letters and two digits, not a DEAN) or another id, e.g. a DEAN."""
    iban = account[:2].isalpha() and account[2:4].isdigit() and not DEAN.match(account)
    return Party(iban=account) if iban else Party(other_id=account)


def credit_transfer_xml(
    *, message_id: str = "TEST-PAY-0001", end_to_end_id: str = "TEST-E2E-0001", amount: str = "120.00",
    debtor: str = "EU4900000000000001", creditor: str = "EU6500000000000004", debtor_agent_bic: str | None = "UNCRITM1XXX",
    creditor_agent_bic: str | None = None, remittance_info: str | None = None, created: datetime = CREATED,
) -> bytes:
    """A valid pacs.008 with one credit transfer."""
    return validate(build_pacs008(CustomerCreditTransfer(message_id, created, [CreditTransfer(
        end_to_end_id, Decimal(amount), _party(debtor), _party(creditor), debtor_agent_bic=debtor_agent_bic,
        creditor_agent_bic=creditor_agent_bic, remittance_info=remittance_info)])))


def status_report_xml(
    *, original_message_id: str, end_to_end_ids: Sequence[str] = ("TEST-E2E-0001",), status: str = SETTLED,
    reason_code: str | None = None, additional_info: str | None = None, message_id: str = "TEST-STS-0001",
    original_message_name_id: str = "pacs.008.001.08", created: datetime = CREATED,
) -> bytes:
    """A valid pacs.002 giving every one of `end_to_end_ids` the same `status` (ACSC settled by default;
    RJCT with a `reason_code` such as AM04, and optionally `additional_info`, rejected)."""
    return validate(build_pacs002(PaymentStatusReport(
        message_id, created, original_message_id, original_message_name_id, group_status=status,
        transactions=[TransactionStatus(status, end_to_end_id, reason_code=reason_code, additional_info=additional_info)
                      for end_to_end_id in end_to_end_ids])))


def rejected_report_xml(*, reason_code: str = "AM04", **kwargs) -> bytes:
    """A valid pacs.002 rejecting (RJCT) with `reason_code`; the rest as `status_report_xml`."""
    return status_report_xml(status=REJECTED, reason_code=reason_code, **kwargs)


def status_request_xml(
    *, original_message_id: str, end_to_end_ids: Sequence[str] = ("TEST-E2E-0001",), message_id: str = "TEST-REQ-0001",
    original_message_name_id: str = "pacs.008.001.08", created: datetime = CREATED,
) -> bytes:
    """A valid pacs.028 asking the status of `end_to_end_ids` of the original message."""
    return validate(build_pacs028(StatusRequest(
        message_id, created, original_message_id, list(end_to_end_ids), original_message_name_id)))


def payment_return_xml(
    *, original_message_id: str, original_end_to_end_id: str = "TEST-E2E-0001", amount: str = "80.00",
    reason_code: str = "AC04", original_debtor: str = "EU6500000000000004", original_creditor: str = "EU4900000000000001",
    return_id: str = "TEST-RTR-0001", message_id: str = "TEST-RTRMSG-0001", created: datetime = CREATED,
) -> bytes:
    """A valid pacs.004 sending back `amount` of one original payment."""
    return validate(build_pacs004(PaymentReturn(message_id, created, [ReturnedTransaction(
        return_id, original_message_id, original_end_to_end_id, Decimal(amount), reason_code,
        _party(original_debtor), _party(original_creditor))])))
