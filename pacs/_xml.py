"""XML helpers shared by the message modules."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

from .exceptions import PacsParseError

NAMESPACE_PREFIX = "urn:iso:std:iso:20022:tech:xsd:"


def namespace(message: str, variant: str) -> str:
    """The namespace URI of e.g. ("pacs.008", "001.08")."""
    return f"{NAMESPACE_PREFIX}{message}.{variant}"


def sub(parent: etree._Element, tag: str, text: str | None = None, **attributes) -> etree._Element:
    """Add a child in the parent's namespace."""
    ns = etree.QName(parent).namespace
    element = etree.SubElement(parent, f"{{{ns}}}{tag}" if ns else tag, **attributes)
    if text is not None:
        element.text = text
    return element


def read_root(data: bytes, message: str, wrapper: str) -> etree._Element:
    """The message wrapper (e.g. FIToFICstmrCdtTrf) of a Document in any variant of `message`."""
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        raise PacsParseError(f"Malformed XML: {exc}") from exc
    qname = etree.QName(root)
    if qname.localname != "Document" or not (qname.namespace or "").startswith(f"{NAMESPACE_PREFIX}{message}."):
        raise PacsParseError(f"Not a {message} Document (root {root.tag}).")
    element = root.find(f"{{{qname.namespace}}}{wrapper}")
    if element is None:
        raise PacsParseError(f"No <{wrapper}> in the {message} Document.")
    return element


class Reader:
    """Find-and-read helpers bound to one namespace."""

    def __init__(self, element: etree._Element):
        self.ns = etree.QName(element).namespace

    def path(self, *tags: str) -> str:
        return "/".join(f"{{{self.ns}}}{tag}" for tag in tags)

    def find(self, element: etree._Element | None, *tags: str) -> etree._Element | None:
        return None if element is None else element.find(self.path(*tags))

    def findall(self, element: etree._Element, *tags: str) -> list[etree._Element]:
        return element.findall(self.path(*tags))

    def text(self, element: etree._Element | None, *tags: str) -> str | None:
        found = self.find(element, *tags)
        return found.text.strip() if found is not None and found.text else None

    def required(self, element: etree._Element | None, *tags: str) -> str:
        value = self.text(element, *tags)
        if value is None:
            raise PacsParseError(f"Missing {'/'.join(tags)}.")
        return value


def parse_decimal(value: str, what: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise PacsParseError(f"Invalid {what}: {value!r}") from exc


def parse_datetime(value: str | None, what: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PacsParseError(f"Invalid {what}: {value!r}") from exc


def iso_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds")
