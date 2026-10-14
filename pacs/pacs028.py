"""pacs.028.001.03 FIToFIPaymentStatusRequest: asking what became of a pacs.008.

A PSP that got no status report for a payment it sent asks the settlement
system about it; the answer is a pacs.002 (`pacs002`), as for the payment itself.
`build_pacs028` writes one, `parse_pacs028` reads one in any pacs.028 variant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree

from ._xml import Reader, iso_datetime, namespace, parse_datetime, read_root, sub
from .exceptions import PacsError, PacsParseError

VARIANT = "001.03"
NAMESPACE = namespace("pacs.028", VARIANT)
MAX_35 = 35


@dataclass
class StatusRequest:
    """A pacs.028 about the transactions of one original message (by their EndToEndIds)."""

    message_id: str
    creation_datetime: datetime
    original_message_id: str
    original_end_to_end_ids: list[str] = field(default_factory=list)
    original_message_name_id: str = "pacs.008.001.08"


def build_pacs028(request: StatusRequest, *, pretty_print: bool = True) -> bytes:
    """The pacs.028.001.03 XML of `request`. Raises `PacsError` if it isn't valid."""
    for name in ("message_id", "original_message_id"):
        value = getattr(request, name)
        if not value or len(value) > MAX_35:
            raise PacsError(f"{name} must be 1 to {MAX_35} characters: {value!r}")
    if not request.original_end_to_end_ids:
        raise PacsError("A pacs.028 asks about at least one transaction.")

    root = etree.Element(f"{{{NAMESPACE}}}Document", nsmap={None: NAMESPACE})
    status_request = sub(root, "FIToFIPmtStsReq")
    header = sub(status_request, "GrpHdr")
    sub(header, "MsgId", request.message_id)
    sub(header, "CreDtTm", iso_datetime(request.creation_datetime))
    original = sub(status_request, "OrgnlGrpInf")
    sub(original, "OrgnlMsgId", request.original_message_id)
    sub(original, "OrgnlMsgNmId", request.original_message_name_id)
    for end_to_end_id in request.original_end_to_end_ids:
        sub(sub(status_request, "TxInf"), "OrgnlEndToEndId", end_to_end_id)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print)


def parse_pacs028(data: bytes) -> StatusRequest:
    """Read a pacs.028 (any variant). Raises `PacsParseError` if it isn't a readable one."""
    status_request = read_root(data, "pacs.028", "FIToFIPmtStsReq")
    read = Reader(status_request)
    header = read.find(status_request, "GrpHdr")
    original = read.find(status_request, "OrgnlGrpInf")
    if header is None or original is None:
        raise PacsParseError("A pacs.028 needs GrpHdr and OrgnlGrpInf.")
    return StatusRequest(
        message_id=read.required(header, "MsgId"),
        creation_datetime=parse_datetime(read.required(header, "CreDtTm"), "CreDtTm"),
        original_message_id=read.required(original, "OrgnlMsgId"),
        original_message_name_id=read.text(original, "OrgnlMsgNmId") or "",
        original_end_to_end_ids=[
            read.required(tx, "OrgnlEndToEndId") for tx in read.findall(status_request, "TxInf")
        ],
    )
