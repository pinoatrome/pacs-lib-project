"""Build and parse ISO 20022 pacs (payments clearing and settlement) messages.

- pacs.008 FIToFICustomerCreditTransfer (`pacs008`): the credit transfer a
  payer's PSP sends for settlement; built and parsed.
- pacs.002 FIToFIPaymentStatusReport (`pacs002`): the settlement system's answer
  to a pacs.008, pacs.028 or pacs.004, accepting or rejecting its transactions;
  built and parsed.
- pacs.028 FIToFIPaymentStatusRequest (`pacs028`): asking what became of a
  pacs.008 whose status report never came; built and parsed. It's answered
  with a pacs.002 too.
- pacs.004 PaymentReturn (`pacs004`): sending back (part of) a settled pacs.008,
  with a reason, e.g. answering a recall (FOCR); built and parsed. It's
  answered with a pacs.002.

Any of them can be checked against ISO 20022's schemas (`validate`, `schema_errors`),
and `pacs.testing` makes valid ones for tests.
"""
from .exceptions import PacsError, PacsParseError
from .models import Party
from .pacs002 import PaymentStatusReport, TransactionStatus, build_pacs002, parse_pacs002
from .pacs004 import PaymentReturn, ReturnedTransaction, build_pacs004, parse_pacs004
from .pacs008 import CreditTransfer, CustomerCreditTransfer, build_pacs008, parse_pacs008
from .pacs028 import StatusRequest, build_pacs028, parse_pacs028
from .validation import PacsValidationError, schema_errors, validate

__all__ = [
    "CreditTransfer",
    "CustomerCreditTransfer",
    "PacsError",
    "PacsParseError",
    "PacsValidationError",
    "Party",
    "PaymentReturn",
    "PaymentStatusReport",
    "ReturnedTransaction",
    "StatusRequest",
    "TransactionStatus",
    "build_pacs002",
    "build_pacs004",
    "build_pacs008",
    "build_pacs028",
    "parse_pacs002",
    "parse_pacs004",
    "parse_pacs008",
    "parse_pacs028",
    "schema_errors",
    "validate",
]
