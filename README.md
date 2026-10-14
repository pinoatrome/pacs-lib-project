# pacs-lib-project

Build and parse ISO 20022 pacs (payments clearing and settlement) XML as typed
Python objects, for a payment service provider talking to a settlement system
such as the Eurosystem's DESP.

| Message | Name | Used for | Functions |
|---|---|---|---|
| pacs.008.001.08 | FIToFICustomerCreditTransfer | a customer's payment, sent for settlement | `build_pacs008`, `parse_pacs008` |
| pacs.002.001.10 | FIToFIPaymentStatusReport | the answer to a pacs.008, pacs.028 or pacs.004: accepted or rejected, per transaction | `build_pacs002`, `parse_pacs002` |
| pacs.028.001.03 | FIToFIPaymentStatusRequest | asking what became of a pacs.008 whose report never came | `build_pacs028`, `parse_pacs028` |
| pacs.004.001.09 | PaymentReturn | sending back (part of) a settled pacs.008, with a reason | `build_pacs004`, `parse_pacs004` |

Parsing matches elements by local name only, so one code path reads the
messages of any variant of a family. Building writes the variant in the table.
Both raise `PacsError` (`PacsParseError` when reading) for what isn't valid:
a missing or over-long id, an amount that isn't positive with two decimals, a
party with no account.

## Install

```bash
pip install -e .          # or: pip install git+https://github.com/pinoatrome/pacs-lib-project
```

## Usage

```python
from datetime import datetime, timezone
from decimal import Decimal

from pacs import CreditTransfer, CustomerCreditTransfer, Party, build_pacs008, parse_pacs008

xml = build_pacs008(CustomerCreditTransfer(
    message_id="PSPPAY-0001",
    creation_datetime=datetime(2026, 10, 6, 10, 12, tzinfo=timezone.utc),
    transactions=[CreditTransfer(
        end_to_end_id="E2E-DEUR-0101",
        amount=Decimal("120.00"),
        debtor=Party(name="Alice Rossi", other_id="DEAN-IT-0001-ALPHA"),
        creditor=Party(name="Shop SRL", iban="IT60X0542811101000000654321"),
        debtor_agent_bic="UNCRITM1XXX",
        remittance_info="Order 2026-1006",
    )],
))

message = parse_pacs008(xml)
for tx in message.transactions:
    print(tx.end_to_end_id, tx.amount, tx.debtor.account_id, "->", tx.creditor.account_id)
```

A party's account is an IBAN or another id (`other_id`, e.g. a DEAN); the
agents' BICs are mandatory in a pacs.008, so one that isn't known is written
`NOTPROVIDED`, as SEPA does, and read back as `None`.

The status report answering it, and the request asking for one:

```python
from pacs import PaymentStatusReport, StatusRequest, TransactionStatus, build_pacs002, build_pacs028, parse_pacs002
```

See each module's docstring (`pacs/pacs002.py`, `pacs004.py`, `pacs028.py`) for
its objects, and `tests/` for more examples.

## Tests

```bash
pip install -e ".[test]"
pytest
```

`tests/test_schemas.py` checks every message the library builds, and every
fixture in `tests/fixtures/`, against the ISO 20022 schemas in `tests/xsd/`:
the Payments Clearing and Settlement set of the catalogue, 2025/2026 edition
(pacs.002.001.16, .004.001.15, .008.001.14, .028.001.07). They are newer
versions than the library writes (the ones TARGET and DESP use), so a message
is checked against the newer version with its namespace changed to that
version's: newer versions mostly add optional elements, so a message valid in
both is valid ISO 20022 in its own version too.
