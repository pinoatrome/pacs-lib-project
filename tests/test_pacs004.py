"""pacs.004 PaymentReturn: building and parsing."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from pacs import PacsError, PacsParseError, Party, PaymentReturn, ReturnedTransaction, build_pacs004, parse_pacs004
from pacs.pacs004 import FOLLOWING_CANCELLATION_REQUEST

FIXTURES = Path(__file__).parent / "fixtures"
NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pacs.004.001.09"}


@pytest.fixture
def two_returns() -> bytes:
    return (FIXTURES / "pacs004_return.xml").read_bytes()


def returned(**changes) -> ReturnedTransaction:
    return ReturnedTransaction(**{
        "return_id": "RTR-0001",
        "original_message_id": "BCIPAY-0042",
        "original_end_to_end_id": "E2E-DEUR-0420",
        "original_amount": Decimal("80.00"),
        "returned_amount": Decimal("80.00"),
        "reason_code": FOLLOWING_CANCELLATION_REQUEST,
        "additional_info": "Recall accepted",
        "original_debtor": Party(name="Bruno Bianchi", other_id="DEAN-IT-0002-BETA"),
        "original_creditor": Party(name="Alice Rossi", other_id="DEAN-IT-0001-ALPHA"),
        "original_debtor_agent_bic": "BCITITMMXXX",
        "original_creditor_agent_bic": "UNCRITM1XXX",
        **changes,
    })


def message(*transactions: ReturnedTransaction, **changes) -> PaymentReturn:
    return PaymentReturn(**{
        "message_id": "PSPRTR-0001",
        "creation_datetime": datetime(2026, 10, 11, 9, 30, tzinfo=timezone.utc),
        "transactions": list(transactions) or [returned()],
        **changes,
    })


def test_build_sends_the_payment_back_with_its_reason():
    root = etree.fromstring(build_pacs004(message()))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:pacs.004.001.09}Document"
    header = root.find("p:PmtRtr/p:GrpHdr", NS)
    assert header.findtext("p:MsgId", namespaces=NS) == "PSPRTR-0001"
    assert header.findtext("p:NbOfTxs", namespaces=NS) == "1"
    total = header.find("p:TtlRtrdIntrBkSttlmAmt", NS)
    assert (total.text, total.get("Ccy")) == ("80.00", "EUR")
    info = root.find("p:PmtRtr/p:TxInf", NS)
    assert info.findtext("p:RtrId", namespaces=NS) == "RTR-0001"
    assert info.findtext("p:OrgnlGrpInf/p:OrgnlMsgId", namespaces=NS) == "BCIPAY-0042"
    assert info.findtext("p:OrgnlGrpInf/p:OrgnlMsgNmId", namespaces=NS) == "pacs.008.001.08"
    assert info.findtext("p:OrgnlEndToEndId", namespaces=NS) == "E2E-DEUR-0420"
    assert info.findtext("p:RtrRsnInf/p:Rsn/p:Cd", namespaces=NS) == "FOCR"
    assert info.findtext("p:OrgnlTxRef/p:Dbtr/p:Pty/p:Nm", namespaces=NS) == "Bruno Bianchi"
    assert info.findtext("p:OrgnlTxRef/p:DbtrAcct/p:Id/p:Othr/p:Id", namespaces=NS) == "DEAN-IT-0002-BETA"
    assert info.findtext("p:OrgnlTxRef/p:CdtrAcct/p:Id/p:Othr/p:Id", namespaces=NS) == "DEAN-IT-0001-ALPHA"
    assert info.findtext("p:OrgnlTxRef/p:CdtrAgt/p:FinInstnId/p:BICFI", namespaces=NS) == "UNCRITM1XXX"


def test_elements_follow_the_schema_order():
    info = etree.fromstring(build_pacs004(message())).find("p:PmtRtr/p:TxInf", NS)

    assert [etree.QName(child).localname for child in info] == [
        "RtrId", "OrgnlGrpInf", "OrgnlEndToEndId", "OrgnlIntrBkSttlmAmt", "RtrdIntrBkSttlmAmt", "ChrgBr",
        "RtrRsnInf", "OrgnlTxRef",
    ]


def test_round_trip():
    original = message(returned(), returned(
        return_id="RTR-0002",
        original_end_to_end_id="E2E-DEUR-0421",
        original_amount=Decimal("50.00"),
        returned_amount=Decimal("20.00"),
        reason_code="MD06",
        additional_info=None,
        original_instruction_id="INSTR-0421",
        original_transaction_id="TX-0421",
    ))

    assert parse_pacs004(build_pacs004(original)) == original
    assert original.total_amount == Decimal("100.00")


def test_a_return_may_be_partial():
    assert returned(returned_amount=Decimal("30.00")).partial
    assert not returned().partial
    assert not returned(original_amount=None).partial


def test_parse_reads_each_return(two_returns):
    payment_return = parse_pacs004(two_returns)

    assert (payment_return.message_id, payment_return.settlement_method) == ("BCIRTR-0001", "CLRG")
    assert payment_return.creation_datetime == datetime(2026, 10, 11, 9, 30, tzinfo=timezone.utc)
    recall, closed = payment_return.transactions
    assert (recall.return_id, recall.original_end_to_end_id, recall.original_instruction_id) == (
        "RTR-0001", "E2E-DEUR-0101", "INSTR-0101",
    )
    assert (recall.reason_code, recall.additional_info) == ("FOCR", "Recall accepted: payment made by mistake")
    assert recall.original_debtor == Party(name="Alice Rossi", other_id="DEAN-IT-0001-ALPHA")
    assert recall.original_creditor == Party(name="Shop SRL", iban="IT60X0542811101000000654321")
    assert (recall.original_debtor_agent_bic, recall.original_creditor_agent_bic) == ("UNCRITM1XXX", "BCITITMMXXX")
    assert (closed.original_amount, closed.returned_amount, closed.currency) == (None, Decimal("45.50"), "EUR")
    assert (closed.original_transaction_id, closed.reason_code) == ("TX-0102", "AC04")
    assert closed.original_creditor == Party(other_id="DEAN-IT-0002-BETA")
    assert payment_return.total_amount == Decimal("165.50")


@pytest.mark.parametrize(
    "transactions, changes, error",
    [
        ([], {"message_id": ""}, "MsgId must be 1 to 35"),
        ([], {"transactions": []}, "at least one returned transaction"),
        ([returned(return_id="R" * 36)], {}, "return_id must be 1 to 35"),
        ([returned(original_end_to_end_id="")], {}, "original_end_to_end_id must be 1 to 35"),
        ([returned(returned_amount=Decimal("0"))], {}, "returned amount .* must be positive"),
        ([returned(returned_amount=Decimal("1.234"))], {}, "at most 2 decimals"),
        ([returned(returned_amount=Decimal("90.00"))], {}, "more than the original"),
        ([returned(reason_code="TOOLONG")], {}, "code of 1 to 4"),
        ([returned(reason_code="focr")], {}, "code of 1 to 4"),
        ([returned(additional_info="x" * 106)], {}, "over 105"),
        ([returned(original_creditor=Party(name="Nobody"))], {}, "original creditor .* has no account"),
        ([returned(), returned(return_id="RTR-0002", currency="USD")], {}, "one currency"),
    ],
    ids=[
        "no-msg-id", "no-transaction", "long-return-id", "no-end-to-end-id", "zero-amount", "three-decimals",
        "more-than-original", "long-reason", "lowercase-reason", "long-info", "no-account", "two-currencies",
    ],
)
def test_invalid_returns_arent_built(transactions, changes, error):
    with pytest.raises(PacsError, match=error):
        build_pacs004(message(*transactions, **changes))


@pytest.mark.parametrize(
    "change, error",
    [
        ((b"<RtrId>RTR-0001</RtrId>", b""), "Missing RtrId"),
        ((b"<Cd>FOCR</Cd>", b""), "Missing RtrRsnInf/Rsn/Cd"),
        ((b'<RtrdIntrBkSttlmAmt Ccy="EUR">45.50</RtrdIntrBkSttlmAmt>', b""), "Missing RtrdIntrBkSttlmAmt"),
        ((b"<NbOfTxs>2</NbOfTxs>", b"<NbOfTxs>3</NbOfTxs>"), "NbOfTxs says 3"),
        ((b"pacs.004.001.09", b"pacs.008.001.08"), "Not a pacs.004 Document"),
    ],
    ids=["no-return-id", "no-reason", "no-amount", "wrong-count", "other-message"],
)
def test_unreadable_returns_are_refused(two_returns, change, error):
    with pytest.raises(PacsParseError, match=error):
        parse_pacs004(two_returns.replace(*change))


def test_a_return_without_the_original_parties_is_refused(two_returns):
    start = two_returns.index(b"<OrgnlTxRef>")
    end = two_returns.index(b"</OrgnlTxRef>") + len(b"</OrgnlTxRef>")

    with pytest.raises(PacsParseError, match="Missing OrgnlTxRef"):
        parse_pacs004(two_returns[:start] + two_returns[end:])
