"""Every pacs message the library builds, and every pacs fixture, against ISO 20022's schemas.

The schemas in pacs/xsd/ are the Payments Clearing and Settlement
message set of the ISO 20022 catalogue, 2025/2026 edition: newer versions than the
library writes (pacs.002.001.10, .004.001.09, .008.001.08, .028.001.03, the ones
TARGET and DESP use). A message is checked against the newer version with its
namespace changed to that version's: newer versions mostly add optional
elements, so a message valid in both is valid ISO 20022 in its own version too.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from pacs import (
    CreditTransfer,
    CustomerCreditTransfer,
    Party,
    PaymentReturn,
    PaymentStatusReport,
    ReturnedTransaction,
    StatusRequest,
    TransactionStatus,
    build_pacs002,
    build_pacs004,
    build_pacs008,
    build_pacs028,
    schema_errors,
)
from pacs.pacs004 import FOLLOWING_CANCELLATION_REQUEST
from pacs.validation import SCHEMA_VERSIONS

FIXTURES = Path(__file__).parent / "fixtures"

NOW = datetime(2026, 10, 11, 9, 30, tzinfo=timezone.utc)
ALICE = Party(name="Alice Rossi", other_id="EU4900000000000001")
SHOP = Party(name="Shop SRL", iban="IT60X0542811101000000654321")


# Each message with every optional element the library can write.
BUILT = {
    "pacs.008": lambda: build_pacs008(CustomerCreditTransfer("PSPPAY-0001", NOW, [
        CreditTransfer(
            "E2E-DEUR-0101", Decimal("120.00"), ALICE, SHOP, instruction_id="INSTR-0101", transaction_id="TX-0101",
            debtor_agent_bic="UNCRITM1XXX", creditor_agent_bic="BCITITMMXXX", remittance_info="Order 2026-1006",
        ),
        CreditTransfer("E2E-DEUR-0102", Decimal("45.50"), ALICE, Party(other_id="EU2200000000000002")),
    ])),
    "pacs.004": lambda: build_pacs004(PaymentReturn("PSPRTR-0001", NOW, [
        ReturnedTransaction(
            "RTR-0001", "BCIPAY-0042", "E2E-DEUR-0420", Decimal("80.00"), FOLLOWING_CANCELLATION_REQUEST,
            original_debtor=Party(name="Bruno Bianchi", other_id="EU2200000000000002"), original_creditor=ALICE,
            original_amount=Decimal("80.00"), original_instruction_id="INSTR-0420", original_transaction_id="TX-0420",
            additional_info="Recall accepted", original_debtor_agent_bic="BCITITMMXXX",
            original_creditor_agent_bic="UNCRITM1XXX",
        ),
        ReturnedTransaction(
            "RTR-0002", "BCIPAY-0042", "E2E-DEUR-0421", Decimal("10.00"), "AC04",
            original_debtor=Party(other_id="EU2200000000000002"), original_creditor=Party(other_id="EU9200000000000003"),
        ),
    ])),
    "pacs.002": lambda: build_pacs002(PaymentStatusReport(
        "DESP-STS-0001", NOW, "PSPPAY-0001", "pacs.008.001.08", group_status="PART", group_reason_code="NARR",
        transactions=[
            TransactionStatus("ACSC", "E2E-DEUR-0101", "INSTR-0101", "TX-0101"),
            TransactionStatus("RJCT", "E2E-DEUR-0102", reason_code="AM04", additional_info="Insufficient funds"),
        ],
    )),
    "pacs.028": lambda: build_pacs028(StatusRequest("PSPSTS-0001", NOW, "PSPPAY-0001", ["E2E-1", "E2E-2"])),
}

FIXTURE_FILES = sorted(
    path.relative_to(FIXTURES) for path in FIXTURES.rglob("pacs0*.xml")
)


@pytest.mark.parametrize("message", BUILT)
def test_built_messages_are_valid(message):
    assert schema_errors(BUILT[message]()) == []


@pytest.mark.parametrize("fixture", FIXTURE_FILES, ids=str)
def test_fixtures_are_valid(fixture):
    assert schema_errors((FIXTURES / fixture).read_bytes()) == []


def test_every_schema_checks_a_built_message():
    assert set(BUILT) == set(SCHEMA_VERSIONS)


def test_the_schemas_refuse_a_misplaced_element():
    """A control: the check isn't vacuous."""
    xml = BUILT["pacs.004"]().replace(b"<ChrgBr>SLEV</ChrgBr>", b"", 1)
    misplaced = xml.replace(b"</RtrRsnInf>", b"</RtrRsnInf><ChrgBr>SLEV</ChrgBr>", 1)

    errors = schema_errors(misplaced)

    assert errors and "ChrgBr" in errors[0]
