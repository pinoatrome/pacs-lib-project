"""pacs.002 FIToFIPaymentStatusReport: building and parsing."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lxml import etree

from pacs import PacsError, PacsParseError, PaymentStatusReport, TransactionStatus, build_pacs002, parse_pacs002

FIXTURES = Path(__file__).parent / "fixtures"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10"}


@pytest.fixture
def settled() -> bytes:
    return (FIXTURES / "pacs002_settled.xml").read_bytes()


@pytest.fixture
def partly_rejected() -> bytes:
    return (FIXTURES / "pacs002_partly_rejected.xml").read_bytes()


def test_group_status_applies_to_every_transaction(settled):
    report = parse_pacs002(settled)

    assert (report.message_id, report.original_message_id, report.original_message_name_id) == (
        "DESP-STS-0001", "PSPPAY-0001", "pacs.008.001.08",
    )
    assert report.creation_datetime == datetime(2026, 10, 6, 10, 12, 1, tzinfo=timezone.utc)
    assert report.group_status == "ACSC"
    assert report.transactions == []
    assert report.status_of("E2E-DEUR-0101") == "ACSC"


def test_each_transaction_has_its_status_and_reason(partly_rejected):
    report = parse_pacs002(partly_rejected)

    settled, rejected = report.transactions
    assert (settled.original_end_to_end_id, settled.original_instruction_id, settled.status) == (
        "E2E-DEUR-0101", "INSTR-0101", "ACSC",
    )
    assert not settled.rejected
    assert rejected.rejected
    assert (rejected.original_transaction_id, rejected.reason_code, rejected.additional_info) == (
        "TX-0102", "AM04", "Insufficient funds on DEAN-IT-0001-ALPHA",
    )
    assert report.status_of("E2E-DEUR-0102") == "RJCT"
    assert report.status_of("E2E-UNKNOWN") == "PART"


@pytest.mark.parametrize(
    "change, error",
    [
        ((b"<GrpSts>ACSC</GrpSts>", b""), "reports no status"),
        ((b"<OrgnlMsgId>PSPPAY-0001</OrgnlMsgId>", b""), "Missing OrgnlMsgId"),
        ((b"pacs.002.001.10", b"pacs.008.001.08"), "Not a pacs.002 Document"),
        ((b"<CreDtTm>2026-10-06T10:12:01.000Z</CreDtTm>", b"<CreDtTm>yesterday</CreDtTm>"), "Invalid CreDtTm"),
    ],
    ids=["no-status", "no-original-msg-id", "other-message", "bad-datetime"],
)
def test_unreadable_reports_are_refused(settled, change, error):
    with pytest.raises(PacsParseError, match=error):
        parse_pacs002(settled.replace(*change))


def test_transaction_without_status_is_refused(partly_rejected):
    with pytest.raises(PacsParseError, match="Missing TxInfAndSts/TxSts"):
        parse_pacs002(partly_rejected.replace(b"<TxSts>ACSC</TxSts>", b""))


# ── Building ─────────────────────────────────────────────────────────────────


def report(**changes) -> PaymentStatusReport:
    return PaymentStatusReport(**{
        "message_id": "DESP-STS-0100",
        "creation_datetime": datetime(2026, 10, 11, 9, 31, tzinfo=timezone.utc),
        "original_message_id": "PSPRTR-0001",
        "original_message_name_id": "pacs.004.001.09",
        "transactions": [TransactionStatus(
            status="ACSC", original_instruction_id="RTR-0001", original_end_to_end_id="E2E-DEUR-0420",
        )],
        **changes,
    })


def test_build_answers_a_return():
    root = etree.fromstring(build_pacs002(report()))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10}Document"
    assert root.findtext("p:FIToFIPmtStsRpt/p:OrgnlGrpInfAndSts/p:OrgnlMsgNmId", namespaces=NS) == "pacs.004.001.09"
    info = root.find("p:FIToFIPmtStsRpt/p:TxInfAndSts", NS)
    assert [etree.QName(child).localname for child in info] == ["OrgnlInstrId", "OrgnlEndToEndId", "TxSts"]
    assert info.findtext("p:TxSts", namespaces=NS) == "ACSC"


@pytest.mark.parametrize("fixture", ["pacs002_settled.xml", "pacs002_partly_rejected.xml"])
def test_round_trip_of_desp_reports(fixture):
    original = parse_pacs002((FIXTURES / fixture).read_bytes())

    assert parse_pacs002(build_pacs002(original)) == original


def test_a_rejection_carries_its_reason():
    rejected = report(group_status="RJCT", group_reason_code="NARR", transactions=[TransactionStatus(
        status="RJCT", original_end_to_end_id="E2E-DEUR-0420", reason_code="AM04", additional_info="No funds",
    )])

    assert parse_pacs002(build_pacs002(rejected)) == rejected


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"message_id": "M" * 36}, "MsgId must be 1 to 35"),
        ({"creation_datetime": None}, "creation time"),
        ({"original_message_id": ""}, "OrgnlMsgId must be 1 to 35"),
        ({"group_status": None, "transactions": []}, "reports a status"),
        ({"transactions": [TransactionStatus(status="ACSC")]}, "which transaction"),
        ({"transactions": [TransactionStatus(status="", original_end_to_end_id="E")]}, "needs its TxSts"),
        ({"transactions": [TransactionStatus(status="RJCT", original_end_to_end_id="E", additional_info="x" * 106)]},
         "AddtlInf must be 1 to 105"),
    ],
    ids=["long-msg-id", "no-time", "no-original", "no-status", "no-reference", "no-tx-status", "long-info"],
)
def test_invalid_reports_arent_built(changes, error):
    with pytest.raises(PacsError, match=error):
        build_pacs002(report(**changes))
