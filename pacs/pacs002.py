"""pacs.002.001.10 FIToFIPaymentStatusReport: the answer to a pacs.008, pacs.028 or pacs.004.

The settlement system reports a status for the whole message (OrgnlGrpInfAndSts)
and/or for each transaction (TxInfAndSts), with a reason when it rejects. Common
status codes: ACSC (settled), ACCP / ACSP (accepted, settlement in progress),
PDNG (pending), RJCT (rejected). `build_pacs002` writes one, `parse_pacs002`
reads any pacs.002 variant.

About a pacs.004, a transaction's status refers to the return by its RtrId, as
OrgnlInstrId, and to the returned payment by its OrgnlEndToEndId.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree

from ._xml import Reader, iso_datetime, namespace, parse_datetime, read_root, sub
from .exceptions import PacsError, PacsParseError

VARIANT = "001.10"
NAMESPACE = namespace("pacs.002", VARIANT)
MAX_35 = 35  # Max35Text: MsgId, the original ids
MAX_105 = 105  # Max105Text: StsRsnInf/AddtlInf

SETTLED = "ACSC"
ACCEPTED = "ACCP"
PENDING = "PDNG"
REJECTED = "RJCT"


@dataclass
class TransactionStatus:
    """One TxInfAndSts: the status of one transaction of the original message."""

    status: str
    original_end_to_end_id: str | None = None
    original_instruction_id: str | None = None
    original_transaction_id: str | None = None
    reason_code: str | None = None
    additional_info: str | None = None

    @property
    def rejected(self) -> bool:
        return self.status == REJECTED


@dataclass
class PaymentStatusReport:
    """A pacs.002 message."""

    message_id: str
    creation_datetime: datetime | None
    original_message_id: str
    original_message_name_id: str | None = None
    group_status: str | None = None
    group_reason_code: str | None = None
    transactions: list[TransactionStatus] = field(default_factory=list)

    def status_of(self, end_to_end_id: str) -> str | None:
        """The status of the transaction with this EndToEndId: its own, else the
        group's (a status for the whole message applies to every transaction)."""
        for tx in self.transactions:
            if tx.original_end_to_end_id == end_to_end_id:
                return tx.status
        return self.group_status


# ── Building ─────────────────────────────────────────────────────────────────


def _check_text(name: str, value: str | None, limit: int, *, required: bool = False) -> None:
    if value is None and not required:
        return
    if not value or len(value) > limit:
        raise PacsError(f"{name} must be 1 to {limit} characters: {value!r}")


def _check(report: PaymentStatusReport) -> None:
    _check_text("MsgId", report.message_id, MAX_35, required=True)
    if report.creation_datetime is None:
        raise PacsError("A pacs.002 needs its creation time (CreDtTm).")
    _check_text("OrgnlMsgId", report.original_message_id, MAX_35, required=True)
    if report.group_status is None and not report.transactions:
        raise PacsError("A pacs.002 reports a status: for the whole message, for its transactions, or both.")
    for tx in report.transactions:
        if not tx.status:
            raise PacsError("Every transaction status needs its TxSts.")
        if not (tx.original_end_to_end_id or tx.original_instruction_id or tx.original_transaction_id):
            raise PacsError(f"A {tx.status} transaction status must say which transaction it's about.")
        for name in ("original_end_to_end_id", "original_instruction_id", "original_transaction_id"):
            _check_text(name, getattr(tx, name), MAX_35)
        _check_text("AddtlInf", tx.additional_info, MAX_105)


def _status_reason(parent: etree._Element, code: str | None, additional_info: str | None) -> None:
    if code is None and additional_info is None:
        return
    reason = sub(parent, "StsRsnInf")
    if code:
        sub(sub(reason, "Rsn"), "Cd", code)
    if additional_info:
        sub(reason, "AddtlInf", additional_info)


def build_pacs002(report: PaymentStatusReport, *, pretty_print: bool = True) -> bytes:
    """The pacs.002.001.10 XML of `report`. Raises `PacsError` if it isn't valid."""
    _check(report)
    root = etree.Element(f"{{{NAMESPACE}}}Document", nsmap={None: NAMESPACE})
    status_report = sub(root, "FIToFIPmtStsRpt")

    header = sub(status_report, "GrpHdr")
    sub(header, "MsgId", report.message_id)
    sub(header, "CreDtTm", iso_datetime(report.creation_datetime))

    original = sub(status_report, "OrgnlGrpInfAndSts")
    sub(original, "OrgnlMsgId", report.original_message_id)
    if report.original_message_name_id:
        sub(original, "OrgnlMsgNmId", report.original_message_name_id)
    if report.group_status:
        sub(original, "GrpSts", report.group_status)
    _status_reason(original, report.group_reason_code, None)

    for tx in report.transactions:
        info = sub(status_report, "TxInfAndSts")
        if tx.original_instruction_id:
            sub(info, "OrgnlInstrId", tx.original_instruction_id)
        if tx.original_end_to_end_id:
            sub(info, "OrgnlEndToEndId", tx.original_end_to_end_id)
        if tx.original_transaction_id:
            sub(info, "OrgnlTxId", tx.original_transaction_id)
        sub(info, "TxSts", tx.status)
        _status_reason(info, tx.reason_code, tx.additional_info)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print)


# ── Parsing ──────────────────────────────────────────────────────────────────

def _reason(read: Reader, element: etree._Element) -> tuple[str | None, str | None]:
    reason = read.find(element, "StsRsnInf")
    return read.text(reason, "Rsn", "Cd"), read.text(reason, "AddtlInf")


def parse_pacs002(data: bytes) -> PaymentStatusReport:
    """Read a pacs.002 (any variant). Raises `PacsParseError` if it isn't a readable one."""
    report = read_root(data, "pacs.002", "FIToFIPmtStsRpt")
    read = Reader(report)
    header = read.find(report, "GrpHdr")
    original = read.find(report, "OrgnlGrpInfAndSts")
    if header is None or original is None:
        raise PacsParseError("A pacs.002 needs GrpHdr and OrgnlGrpInfAndSts.")

    transactions = []
    for info in read.findall(report, "TxInfAndSts"):
        status = read.text(info, "TxSts")
        if status is None:
            raise PacsParseError("Missing TxInfAndSts/TxSts.")
        reason_code, additional_info = _reason(read, info)
        transactions.append(TransactionStatus(
            status=status,
            original_end_to_end_id=read.text(info, "OrgnlEndToEndId"),
            original_instruction_id=read.text(info, "OrgnlInstrId"),
            original_transaction_id=read.text(info, "OrgnlTxId"),
            reason_code=reason_code,
            additional_info=additional_info,
        ))

    group_status = read.text(original, "GrpSts")
    if group_status is None and not transactions:
        raise PacsParseError("The pacs.002 reports no status: neither GrpSts nor TxInfAndSts.")
    group_reason_code, _ = _reason(read, original)
    return PaymentStatusReport(
        message_id=read.required(header, "MsgId"),
        creation_datetime=parse_datetime(read.text(header, "CreDtTm"), "CreDtTm"),
        original_message_id=read.required(original, "OrgnlMsgId"),
        original_message_name_id=read.text(original, "OrgnlMsgNmId"),
        group_status=group_status,
        group_reason_code=group_reason_code,
        transactions=transactions,
    )
