"""pacs.028 FIToFIPaymentStatusRequest: building and parsing."""
from datetime import datetime, timezone

import pytest
from lxml import etree

from pacs import PacsError, PacsParseError, StatusRequest, build_pacs028, parse_pacs028

NS = {"p": "urn:iso:std:iso:20022:tech:xsd:pacs.028.001.03"}


def request(**changes) -> StatusRequest:
    return StatusRequest(**{
        "message_id": "PSPSTS-0001",
        "creation_datetime": datetime(2026, 10, 10, 12, 30, tzinfo=timezone.utc),
        "original_message_id": "PSPPAY-0001",
        "original_end_to_end_ids": ["E2E-DEUR-0101"],
        **changes,
    })


def test_build_asks_about_the_original_transactions():
    root = etree.fromstring(build_pacs028(request(original_end_to_end_ids=["E2E-1", "E2E-2"])))

    assert root.tag == "{urn:iso:std:iso:20022:tech:xsd:pacs.028.001.03}Document"
    assert root.findtext("p:FIToFIPmtStsReq/p:GrpHdr/p:MsgId", namespaces=NS) == "PSPSTS-0001"
    assert root.findtext("p:FIToFIPmtStsReq/p:OrgnlGrpInf/p:OrgnlMsgId", namespaces=NS) == "PSPPAY-0001"
    assert root.findtext("p:FIToFIPmtStsReq/p:OrgnlGrpInf/p:OrgnlMsgNmId", namespaces=NS) == "pacs.008.001.08"
    assert [e.text for e in root.findall("p:FIToFIPmtStsReq/p:TxInf/p:OrgnlEndToEndId", namespaces=NS)] == [
        "E2E-1", "E2E-2",
    ]


def test_round_trip():
    original = request()

    assert parse_pacs028(build_pacs028(original)) == original


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"message_id": ""}, "message_id must be 1 to 35"),
        ({"original_message_id": "M" * 36}, "original_message_id must be 1 to 35"),
        ({"original_end_to_end_ids": []}, "at least one transaction"),
    ],
)
def test_invalid_requests_arent_built(changes, error):
    with pytest.raises(PacsError, match=error):
        build_pacs028(request(**changes))


def test_unreadable_requests_are_refused():
    body = build_pacs028(request())

    with pytest.raises(PacsParseError, match="Missing OrgnlMsgId"):
        parse_pacs028(body.replace(b"<OrgnlMsgId>PSPPAY-0001</OrgnlMsgId>", b""))
    with pytest.raises(PacsParseError, match="Not a pacs.028 Document"):
        parse_pacs028(body.replace(b"pacs.028.001.03", b"pacs.008.001.08"))
