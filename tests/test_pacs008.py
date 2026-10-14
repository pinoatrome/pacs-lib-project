"""pacs.008 FIToFICustomerCreditTransfer: building and parsing."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from pacs import CreditTransfer, CustomerCreditTransfer, PacsError, PacsParseError, Party, build_pacs008, parse_pacs008

FIXTURES = Path(__file__).parent / "fixtures"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"}


@pytest.fixture
def two_payments() -> bytes:
    return (FIXTURES / "pacs008_two_payments.xml").read_bytes()


def message(**changes) -> CustomerCreditTransfer:
    transfer = {
        "end_to_end_id": "E2E-DEUR-0101",
        "amount": Decimal("120.00"),
        "debtor": Party(name="Alice Rossi", other_id="DEAN-IT-0001-ALPHA"),
        "creditor": Party(name="Shop SRL", iban="IT60X0542811101000000654321"),
        "debtor_agent_bic": "UNCRITM1XXX",
        "creditor_agent_bic": "BCITITMMXXX",
        "remittance_info": "Order 2026-1006",
        **changes,
    }
    return CustomerCreditTransfer(
        message_id="PSPPAY-0001",
        creation_datetime=datetime(2026, 10, 6, 10, 12, tzinfo=timezone.utc),
        transactions=[CreditTransfer(**transfer)],
    )


# ── Parsing ──────────────────────────────────────────────────────────────────


def test_parses_the_header_and_every_transfer(two_payments):
    parsed = parse_pacs008(two_payments)

    assert (parsed.message_id, parsed.settlement_method) == ("PSPPAY-0001", "CLRG")
    assert parsed.creation_datetime == datetime(2026, 10, 6, 10, 12, tzinfo=timezone.utc)
    assert parsed.total_amount == Decimal("165.50")
    first, second = parsed.transactions
    assert (first.end_to_end_id, first.instruction_id, first.amount, first.currency) == (
        "E2E-DEUR-0101", "INSTR-0101", Decimal("120.00"), "EUR",
    )
    assert first.debtor == Party(name="Alice Rossi", other_id="DEAN-IT-0001-ALPHA")
    assert first.creditor.account_id == "DEAN-IT-0002-BETA"
    assert (first.debtor_agent_bic, first.creditor_agent_bic) == ("UNCRITM1XXX", "BCITITMMXXX")
    assert first.remittance_info == "Order 2026-1006"
    assert (second.transaction_id, second.creditor.iban, second.remittance_info) == (
        "TX-0102", "IT60X0542811101000000654321", None,
    )


def test_other_variants_are_read_too(two_payments):
    parsed = parse_pacs008(two_payments.replace(b"pacs.008.001.08", b"pacs.008.001.10"))

    assert len(parsed.transactions) == 2


@pytest.mark.parametrize(
    "change, error",
    [
        ((b"<NbOfTxs>2</NbOfTxs>", b"<NbOfTxs>3</NbOfTxs>"), "NbOfTxs says 3"),
        ((b"<EndToEndId>E2E-DEUR-0101</EndToEndId>", b""), "Missing PmtId/EndToEndId"),
        ((b"<MsgId>PSPPAY-0001</MsgId>", b""), "Missing MsgId"),
        ((b'Ccy="EUR">120.00<', b'Ccy="EUR">12O.00<'), "Invalid IntrBkSttlmAmt"),
        ((b"pacs.008.001.08", b"pacs.002.001.10"), "Not a pacs.008 Document"),
        ((b"<FIToFICstmrCdtTrf>", b"<Other>"), "Malformed XML"),
    ],
    ids=["count", "end-to-end-id", "msg-id", "amount", "other-message", "malformed"],
)
def test_unreadable_messages_are_refused(two_payments, change, error):
    with pytest.raises(PacsParseError, match=error):
        parse_pacs008(two_payments.replace(*change))


def test_message_without_transfers_is_refused(two_payments):
    start = two_payments.index(b"<CdtTrfTxInf>")
    end = two_payments.rindex(b"</CdtTrfTxInf>") + len(b"</CdtTrfTxInf>")

    with pytest.raises(PacsParseError, match="No CdtTrfTxInf"):
        parse_pacs008(two_payments[:start] + two_payments[end:])


# ── Building ─────────────────────────────────────────────────────────────────


def test_build_writes_a_pacs008(two_payments):
    root = etree.fromstring(build_pacs008(message()))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08}Document"
    assert root.findtext("p:FIToFICstmrCdtTrf/p:GrpHdr/p:NbOfTxs", namespaces=NS) == "1"
    info = root.find("p:FIToFICstmrCdtTrf/p:CdtTrfTxInf", namespaces=NS)
    assert info.find("p:IntrBkSttlmAmt", namespaces=NS).get("Ccy") == "EUR"
    assert info.findtext("p:DbtrAcct/p:Id/p:Othr/p:Id", namespaces=NS) == "DEAN-IT-0001-ALPHA"
    assert info.findtext("p:CdtrAcct/p:Id/p:IBAN", namespaces=NS) == "IT60X0542811101000000654321"
    # Schema order: debtor side, then creditor agent, creditor, its account.
    assert [etree.QName(child).localname for child in info] == [
        "PmtId", "IntrBkSttlmAmt", "ChrgBr", "Dbtr", "DbtrAcct", "DbtrAgt", "CdtrAgt", "Cdtr", "CdtrAcct", "RmtInf",
    ]


def test_round_trip(two_payments):
    parsed = parse_pacs008(two_payments)

    assert parse_pacs008(build_pacs008(parsed)) == parsed


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"amount": Decimal("0")}, "Amount must be positive"),
        ({"amount": Decimal("1.005")}, "at most 2 decimals"),
        ({"end_to_end_id": "E" * 36}, "end_to_end_id must be 1 to 35"),
        ({"currency": "EURO"}, "3-letter code"),
        ({"creditor": Party(name="No account")}, "creditor of E2E-DEUR-0101 has no account"),
    ],
    ids=["zero", "decimals", "end-to-end-id", "currency", "no-account"],
)
def test_invalid_transfers_arent_built(changes, error):
    with pytest.raises(PacsError, match=error):
        build_pacs008(message(**changes))


def test_message_needs_a_transfer():
    empty = message()
    empty.transactions = []

    with pytest.raises(PacsError, match="at least one credit transfer"):
        build_pacs008(empty)


def test_an_unknown_agent_is_written_not_provided():
    """Both agents are mandatory: the payee's PSP, unknown to the payer's, is NOTPROVIDED."""
    xml = build_pacs008(message(creditor_agent_bic=None))
    info = etree.fromstring(xml).find("p:FIToFICstmrCdtTrf/p:CdtTrfTxInf", NS)

    assert info.findtext("p:CdtrAgt/p:FinInstnId/p:Othr/p:Id", namespaces=NS) == "NOTPROVIDED"
    assert info.find("p:CdtrAgt/p:FinInstnId/p:BICFI", NS) is None
    assert parse_pacs008(xml).transactions[0].creditor_agent_bic is None
