"""pacs.004.001.09 PaymentReturn: sending back a settled credit transfer.

The creditor's PSP returns (part of) a pacs.008 it received: the money goes from
the original creditor back to the original debtor, with a reason. A return may
follow a recall (camt.056 FIToFIPaymentCancellationRequest, answered with
reason FOCR) or come on the PSP's own initiative (e.g. AC04, a closed account).
The settlement system answers it with a pacs.002 (`pacs002`).

`build_pacs004` writes one, `parse_pacs004` reads one in any pacs.004 variant.
The original transaction's parties go in `OrgnlTxRef`, as in the original
pacs.008: its debtor (who gets the money back) and its creditor (who returns it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from lxml import etree

from ._parties import account, agent, party, read_agent, read_party
from ._xml import Reader, iso_datetime, namespace, parse_datetime, parse_decimal, read_root, sub
from .exceptions import PacsError, PacsParseError
from .models import Party

VARIANT = "001.09"
NAMESPACE = namespace("pacs.004", VARIANT)
MAX_35 = 35  # ISO 20022 Max35Text: MsgId, RtrId, the original ids
MAX_105 = 105  # Max105Text: RtrRsnInf/AddtlInf

# ExternalReturnReason1Code: a code of 1 to 4 letters or digits. Some common ones:
CLOSED_ACCOUNT = "AC04"
BLOCKED_ACCOUNT = "AC06"
DUPLICATE = "AM05"
REQUESTED_BY_CUSTOMER = "CUST"
FOLLOWING_CANCELLATION_REQUEST = "FOCR"  # answering a recall (camt.056)
REFUND_REQUEST = "MD06"
NOT_SPECIFIED_CUSTOMER = "MS02"
NOT_SPECIFIED_AGENT = "MS03"
_REASON_CODE = re.compile(r"^[A-Z0-9]{1,4}$")


@dataclass
class ReturnedTransaction:
    """One TxInf: (part of) an original credit transfer sent back."""

    return_id: str
    original_message_id: str
    original_end_to_end_id: str
    returned_amount: Decimal
    reason_code: str
    original_debtor: Party
    original_creditor: Party
    currency: str = "EUR"
    original_amount: Decimal | None = None
    original_message_name_id: str = "pacs.008.001.08"
    original_instruction_id: str | None = None
    original_transaction_id: str | None = None
    additional_info: str | None = None
    original_debtor_agent_bic: str | None = None
    original_creditor_agent_bic: str | None = None

    @property
    def partial(self) -> bool:
        """Less than the original amount is sent back (known only when the original amount is given)."""
        return self.original_amount is not None and self.returned_amount < self.original_amount


@dataclass
class PaymentReturn:
    """A pacs.004 message: a group header and its returned transactions."""

    message_id: str
    creation_datetime: datetime
    transactions: list[ReturnedTransaction] = field(default_factory=list)
    settlement_method: str = "CLRG"

    @property
    def total_amount(self) -> Decimal:
        return sum((tx.returned_amount for tx in self.transactions), Decimal("0"))


# ── Building ─────────────────────────────────────────────────────────────────


def _check_id(name: str, value: str | None, *, required: bool) -> None:
    if value is None and not required:
        return
    if not value or len(value) > MAX_35:
        raise PacsError(f"{name} must be 1 to {MAX_35} characters: {value!r}")


def _check_amount(name: str, value: Decimal) -> None:
    if value <= 0 or value != value.quantize(Decimal("0.01")):
        raise PacsError(f"{name} must be positive, with at most 2 decimals: {value}")


def _check(message: PaymentReturn) -> None:
    _check_id("MsgId", message.message_id, required=True)
    if not message.transactions:
        raise PacsError("A pacs.004 needs at least one returned transaction.")
    currencies = {tx.currency for tx in message.transactions}
    if len(currencies) > 1:
        raise PacsError(f"All the returned transactions must be in one currency, not {sorted(currencies)}.")
    for tx in message.transactions:
        _check_id("return_id", tx.return_id, required=True)
        _check_id("original_message_id", tx.original_message_id, required=True)
        _check_id("original_end_to_end_id", tx.original_end_to_end_id, required=True)
        _check_id("original_instruction_id", tx.original_instruction_id, required=False)
        _check_id("original_transaction_id", tx.original_transaction_id, required=False)
        _check_amount(f"The returned amount of {tx.return_id}", tx.returned_amount)
        if tx.original_amount is not None:
            _check_amount(f"The original amount of {tx.return_id}", tx.original_amount)
            if tx.returned_amount > tx.original_amount:
                raise PacsError(
                    f"{tx.return_id} returns {tx.returned_amount}, more than the original {tx.original_amount}."
                )
        if len(tx.currency) != 3:
            raise PacsError(f"Currency must be a 3-letter code: {tx.currency!r}")
        if not _REASON_CODE.match(tx.reason_code or ""):
            raise PacsError(f"The return reason must be a code of 1 to 4 letters or digits: {tx.reason_code!r}")
        if tx.additional_info is not None and len(tx.additional_info) > MAX_105:
            raise PacsError(f"The reason's additional information is over {MAX_105} characters.")
        for role, who in (("original debtor", tx.original_debtor), ("original creditor", tx.original_creditor)):
            if not who.account_id:
                raise PacsError(f"The {role} of {tx.return_id} has no account (IBAN or other id).")


def build_pacs004(message: PaymentReturn, *, pretty_print: bool = True) -> bytes:
    """The pacs.004.001.09 XML of `message`. Raises `PacsError` if it isn't valid."""
    _check(message)
    root = etree.Element(f"{{{NAMESPACE}}}Document", nsmap={None: NAMESPACE})
    payment_return = sub(root, "PmtRtr")

    header = sub(payment_return, "GrpHdr")
    sub(header, "MsgId", message.message_id)
    sub(header, "CreDtTm", iso_datetime(message.creation_datetime))
    sub(header, "NbOfTxs", str(len(message.transactions)))
    sub(header, "TtlRtrdIntrBkSttlmAmt", f"{message.total_amount:.2f}", Ccy=message.transactions[0].currency)
    sub(sub(header, "SttlmInf"), "SttlmMtd", message.settlement_method)

    for tx in message.transactions:
        info = sub(payment_return, "TxInf")
        sub(info, "RtrId", tx.return_id)
        original_group = sub(info, "OrgnlGrpInf")
        sub(original_group, "OrgnlMsgId", tx.original_message_id)
        sub(original_group, "OrgnlMsgNmId", tx.original_message_name_id)
        if tx.original_instruction_id:
            sub(info, "OrgnlInstrId", tx.original_instruction_id)
        sub(info, "OrgnlEndToEndId", tx.original_end_to_end_id)
        if tx.original_transaction_id:
            sub(info, "OrgnlTxId", tx.original_transaction_id)
        if tx.original_amount is not None:
            sub(info, "OrgnlIntrBkSttlmAmt", f"{tx.original_amount:.2f}", Ccy=tx.currency)
        sub(info, "RtrdIntrBkSttlmAmt", f"{tx.returned_amount:.2f}", Ccy=tx.currency)
        sub(info, "ChrgBr", "SLEV")
        reason = sub(info, "RtrRsnInf")
        sub(sub(reason, "Rsn"), "Cd", tx.reason_code)
        if tx.additional_info:
            sub(reason, "AddtlInf", tx.additional_info)

        # The original transaction's parties, as in its pacs.008.
        reference = sub(info, "OrgnlTxRef")
        party(sub(reference, "Dbtr"), "Pty", tx.original_debtor)
        account(reference, "DbtrAcct", tx.original_debtor)
        agent(reference, "DbtrAgt", tx.original_debtor_agent_bic)
        agent(reference, "CdtrAgt", tx.original_creditor_agent_bic)
        party(sub(reference, "Cdtr"), "Pty", tx.original_creditor)
        account(reference, "CdtrAcct", tx.original_creditor)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print)


# ── Parsing ──────────────────────────────────────────────────────────────────


def _amount(read: Reader, info: etree._Element, tag: str, *, required: bool) -> tuple[Decimal | None, str | None]:
    element = read.find(info, tag)
    if element is None or not element.text:
        if required:
            raise PacsParseError(f"Missing {tag}.")
        return None, None
    return parse_decimal(element.text.strip(), tag), element.get("Ccy")


def parse_pacs004(data: bytes) -> PaymentReturn:
    """Read a pacs.004 (any variant). Raises `PacsParseError` if it isn't a readable one."""
    payment_return = read_root(data, "pacs.004", "PmtRtr")
    read = Reader(payment_return)
    header = read.find(payment_return, "GrpHdr")
    if header is None:
        raise PacsParseError("Missing GrpHdr.")

    transactions = []
    for info in read.findall(payment_return, "TxInf"):
        returned_amount, currency = _amount(read, info, "RtrdIntrBkSttlmAmt", required=True)
        original_amount, _ = _amount(read, info, "OrgnlIntrBkSttlmAmt", required=False)
        reference = read.find(info, "OrgnlTxRef")
        if reference is None:
            raise PacsParseError("Missing OrgnlTxRef: the original transaction's parties.")
        transactions.append(ReturnedTransaction(
            return_id=read.required(info, "RtrId"),
            original_message_id=read.required(info, "OrgnlGrpInf", "OrgnlMsgId"),
            original_message_name_id=read.text(info, "OrgnlGrpInf", "OrgnlMsgNmId") or "",
            original_instruction_id=read.text(info, "OrgnlInstrId"),
            original_end_to_end_id=read.required(info, "OrgnlEndToEndId"),
            original_transaction_id=read.text(info, "OrgnlTxId"),
            original_amount=original_amount,
            returned_amount=returned_amount,
            currency=currency or "",
            reason_code=read.required(info, "RtrRsnInf", "Rsn", "Cd"),
            additional_info=read.text(info, "RtrRsnInf", "AddtlInf"),
            original_debtor=read_party(read, reference, ("Dbtr", "Pty", "Nm"), "DbtrAcct"),
            original_creditor=read_party(read, reference, ("Cdtr", "Pty", "Nm"), "CdtrAcct"),
            original_debtor_agent_bic=read_agent(read, reference, "DbtrAgt"),
            original_creditor_agent_bic=read_agent(read, reference, "CdtrAgt"),
        ))
    if not transactions:
        raise PacsParseError("No TxInf in the pacs.004.")

    number = read.text(header, "NbOfTxs")
    if number is not None and number != str(len(transactions)):
        raise PacsParseError(f"NbOfTxs says {number}, the message has {len(transactions)} transactions.")
    return PaymentReturn(
        message_id=read.required(header, "MsgId"),
        creation_datetime=parse_datetime(read.required(header, "CreDtTm"), "CreDtTm"),
        transactions=transactions,
        settlement_method=read.text(header, "SttlmInf", "SttlmMtd") or "",
    )
