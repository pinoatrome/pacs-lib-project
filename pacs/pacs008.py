"""pacs.008.001.08 FIToFICustomerCreditTransfer: credit transfers sent for settlement.

`build_pacs008` writes one, `parse_pacs008` reads one in any pacs.008 variant
(the elements used here are the same across them). The debtor's and the
creditor's agents are mandatory: one whose BIC isn't known (the payee's PSP,
which only the settlement system may know) is written NOTPROVIDED, as SEPA does,
and read back as None.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from lxml import etree

from ._parties import account, agent, party, read_agent, read_party
from ._xml import Reader, iso_datetime, namespace, parse_datetime, parse_decimal, read_root, sub
from .exceptions import PacsError, PacsParseError
from .models import Party

VARIANT = "001.08"
NAMESPACE = namespace("pacs.008", VARIANT)
MAX_35 = 35  # ISO 20022 Max35Text: MsgId, EndToEndId, InstrId, TxId


@dataclass
class CreditTransfer:
    """One CdtTrfTxInf: a payment from the debtor's account to the creditor's."""

    end_to_end_id: str
    amount: Decimal
    debtor: Party
    creditor: Party
    currency: str = "EUR"
    instruction_id: str | None = None
    transaction_id: str | None = None
    debtor_agent_bic: str | None = None
    creditor_agent_bic: str | None = None
    remittance_info: str | None = None


@dataclass
class CustomerCreditTransfer:
    """A pacs.008 message: a group header and its credit transfers."""

    message_id: str
    creation_datetime: datetime
    transactions: list[CreditTransfer] = field(default_factory=list)
    settlement_method: str = "CLRG"

    @property
    def total_amount(self) -> Decimal:
        return sum((tx.amount for tx in self.transactions), Decimal("0"))


# ── Building ─────────────────────────────────────────────────────────────────


def _check(message: CustomerCreditTransfer) -> None:
    if not message.message_id or len(message.message_id) > MAX_35:
        raise PacsError(f"MsgId must be 1 to {MAX_35} characters: {message.message_id!r}")
    if not message.transactions:
        raise PacsError("A pacs.008 needs at least one credit transfer.")
    for tx in message.transactions:
        for name in ("end_to_end_id", "instruction_id", "transaction_id"):
            value = getattr(tx, name)
            if value is not None and (not value or len(value) > MAX_35):
                raise PacsError(f"{name} must be 1 to {MAX_35} characters: {value!r}")
        if tx.amount <= 0 or tx.amount != tx.amount.quantize(Decimal("0.01")):
            raise PacsError(f"Amount must be positive, with at most 2 decimals: {tx.amount}")
        if len(tx.currency) != 3:
            raise PacsError(f"Currency must be a 3-letter code: {tx.currency!r}")
        for role, who in (("debtor", tx.debtor), ("creditor", tx.creditor)):
            if not who.account_id:
                raise PacsError(f"The {role} of {tx.end_to_end_id} has no account (IBAN or other id).")


def build_pacs008(message: CustomerCreditTransfer, *, pretty_print: bool = True) -> bytes:
    """The pacs.008.001.08 XML of `message`. Raises `PacsError` if it isn't valid."""
    _check(message)
    root = etree.Element(f"{{{NAMESPACE}}}Document", nsmap={None: NAMESPACE})
    transfer = sub(root, "FIToFICstmrCdtTrf")

    header = sub(transfer, "GrpHdr")
    sub(header, "MsgId", message.message_id)
    sub(header, "CreDtTm", iso_datetime(message.creation_datetime))
    sub(header, "NbOfTxs", str(len(message.transactions)))
    sub(header, "TtlIntrBkSttlmAmt", f"{message.total_amount:.2f}", Ccy=message.transactions[0].currency)
    sub(sub(header, "SttlmInf"), "SttlmMtd", message.settlement_method)

    for tx in message.transactions:
        info = sub(transfer, "CdtTrfTxInf")
        payment_id = sub(info, "PmtId")
        if tx.instruction_id:
            sub(payment_id, "InstrId", tx.instruction_id)
        sub(payment_id, "EndToEndId", tx.end_to_end_id)
        if tx.transaction_id:
            sub(payment_id, "TxId", tx.transaction_id)
        sub(info, "IntrBkSttlmAmt", f"{tx.amount:.2f}", Ccy=tx.currency)
        sub(info, "ChrgBr", "SLEV")
        party(info, "Dbtr", tx.debtor)
        account(info, "DbtrAcct", tx.debtor)
        # Both agents are mandatory in a pacs.008: an unknown one is NOTPROVIDED.
        agent(info, "DbtrAgt", tx.debtor_agent_bic, required=True)
        agent(info, "CdtrAgt", tx.creditor_agent_bic, required=True)
        party(info, "Cdtr", tx.creditor)
        account(info, "CdtrAcct", tx.creditor)
        if tx.remittance_info:
            sub(sub(info, "RmtInf"), "Ustrd", tx.remittance_info)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print)


# ── Parsing ──────────────────────────────────────────────────────────────────


def parse_pacs008(data: bytes) -> CustomerCreditTransfer:
    """Read a pacs.008 (any variant). Raises `PacsParseError` if it isn't a readable one."""
    transfer = read_root(data, "pacs.008", "FIToFICstmrCdtTrf")
    read = Reader(transfer)
    header = read.find(transfer, "GrpHdr")
    if header is None:
        raise PacsParseError("Missing GrpHdr.")

    transactions = []
    for info in read.findall(transfer, "CdtTrfTxInf"):
        amount = read.find(info, "IntrBkSttlmAmt")
        if amount is None or not amount.text:
            raise PacsParseError("Missing IntrBkSttlmAmt.")
        transactions.append(CreditTransfer(
            end_to_end_id=read.required(info, "PmtId", "EndToEndId"),
            instruction_id=read.text(info, "PmtId", "InstrId"),
            transaction_id=read.text(info, "PmtId", "TxId"),
            amount=parse_decimal(amount.text.strip(), "IntrBkSttlmAmt"),
            currency=amount.get("Ccy") or "",
            debtor=read_party(read, info, ("Dbtr", "Nm"), "DbtrAcct"),
            creditor=read_party(read, info, ("Cdtr", "Nm"), "CdtrAcct"),
            debtor_agent_bic=read_agent(read, info, "DbtrAgt"),
            creditor_agent_bic=read_agent(read, info, "CdtrAgt"),
            remittance_info=read.text(info, "RmtInf", "Ustrd"),
        ))
    if not transactions:
        raise PacsParseError("No CdtTrfTxInf in the pacs.008.")

    number = read.text(header, "NbOfTxs")
    if number is not None and number != str(len(transactions)):
        raise PacsParseError(f"NbOfTxs says {number}, the message has {len(transactions)} transactions.")
    return CustomerCreditTransfer(
        message_id=read.required(header, "MsgId"),
        creation_datetime=parse_datetime(read.required(header, "CreDtTm"), "CreDtTm"),
        transactions=transactions,
        settlement_method=read.text(header, "SttlmInf", "SttlmMtd") or "",
    )
