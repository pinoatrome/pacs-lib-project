"""Check a pacs document against ISO 20022's schemas (the XSDs in `pacs/xsd/`).

The schemas are the Payments Clearing and Settlement message set of the catalogue,
2025/2026 edition: newer versions than the library writes (pacs.002.001.10,
.004.001.09, .008.001.08, .028.001.03), the ones TARGET and DESP use. A document is
checked against the newer version with its namespace changed to that version's:
newer versions mostly add optional elements, so a document valid in both is valid
ISO 20022 in its own version too.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path

from lxml import etree

from .exceptions import PacsError

SCHEMAS = Path(__file__).parent / "xsd"

# The schema checking each message: its message name -> the version in SCHEMAS.
SCHEMA_VERSIONS = {
    "pacs.002": "pacs.002.001.16",
    "pacs.004": "pacs.004.001.15",
    "pacs.008": "pacs.008.001.14",
    "pacs.028": "pacs.028.001.07",
}


class PacsValidationError(PacsError):
    """A document isn't valid against its schema; `errors` are the schema's findings."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Not valid ISO 20022: " + "; ".join(errors[:3]) + (" ..." if len(errors) > 3 else ""))


@cache
def _schema(version: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / f"{version}.xsd")))


def schema_errors(xml: bytes) -> list[str]:
    """What the schema of `xml`'s message finds wrong in it; empty when it's valid.

    A document that isn't XML, or isn't a pacs message the library knows (pacs.002,
    .004, .008, .028), is one error.
    """
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        return [f"not XML: {exc}"]
    namespace = etree.QName(root).namespace or ""
    own_version = namespace.rsplit(":", 1)[-1]
    version = SCHEMA_VERSIONS.get(own_version[:8])
    if not namespace.startswith("urn:iso:std:iso:20022:tech:xsd:pacs.") or version is None:
        return [f"not a pacs message the library knows: namespace {namespace!r}"]
    checker = _schema(version)
    if checker.validate(etree.fromstring(xml.replace(own_version.encode(), version.encode(), 1))):
        return []
    return [error.message for error in checker.error_log]


def validate(xml: bytes) -> bytes:
    """`xml`, if it's valid against its schema; raises `PacsValidationError` if not."""
    errors = schema_errors(xml)
    if errors:
        raise PacsValidationError(errors)
    return xml
