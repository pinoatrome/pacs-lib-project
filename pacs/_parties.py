"""The debtor, creditor and agent elements the credit transfer and its return share."""
from __future__ import annotations

from lxml import etree

from ._xml import Reader, sub
from .models import Party


def party(parent: etree._Element, tag: str, value: Party) -> etree._Element:
    """`<tag><Nm>` (the name only, if any)."""
    element = sub(parent, tag)
    if value.name:
        sub(element, "Nm", value.name)
    return element


def account(parent: etree._Element, tag: str, value: Party) -> None:
    """`<tag><Id>`: the IBAN, else another id (`Othr/Id`, e.g. a DEAN)."""
    account_id = sub(sub(parent, tag), "Id")
    if value.iban:
        sub(account_id, "IBAN", value.iban)
    else:
        sub(sub(account_id, "Othr"), "Id", value.other_id)


# The id of an agent whose BIC isn't known (`FinInstnId/Othr/Id`), as SEPA writes it.
NOT_PROVIDED = "NOTPROVIDED"


def agent(parent: etree._Element, tag: str, bic: str | None, *, required: bool = False) -> None:
    """`<tag><FinInstnId><BICFI>`. Without a BIC, nothing, or, when the message
    requires the agent (a pacs.008's DbtrAgt and CdtrAgt), `Othr/Id` NOTPROVIDED."""
    if bic:
        sub(sub(sub(parent, tag), "FinInstnId"), "BICFI", bic)
    elif required:
        sub(sub(sub(sub(parent, tag), "FinInstnId"), "Othr"), "Id", NOT_PROVIDED)


def read_agent(read: Reader, parent: etree._Element, tag: str) -> str | None:
    """The BIC of the agent at `tag`; None when there's none (absent, or NOTPROVIDED)."""
    return read.text(parent, tag, "FinInstnId", "BICFI")


def read_party(read: Reader, parent: etree._Element, name_path: tuple[str, ...], account_tag: str) -> Party:
    """The party whose name is at `name_path` and account at `account_tag`, under `parent`."""
    return Party(
        name=read.text(parent, *name_path),
        iban=read.text(parent, account_tag, "Id", "IBAN"),
        other_id=read.text(parent, account_tag, "Id", "Othr", "Id"),
    )
