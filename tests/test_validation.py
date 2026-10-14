"""`validate` and `schema_errors`: the schema check any caller can make."""
import pytest

from pacs import PacsError, PacsValidationError, schema_errors, validate
from pacs.testing import credit_transfer_xml, payment_return_xml


def test_a_valid_document_is_returned_as_it_is():
    xml = credit_transfer_xml()
    assert validate(xml) is xml
    assert schema_errors(xml) == []


def test_a_misplaced_element_is_refused_with_the_schemas_finding():
    xml = payment_return_xml(original_message_id="PSP-0001")
    misplaced = xml.replace(b"<ChrgBr>SLEV</ChrgBr>", b"", 1).replace(
        b"</RtrRsnInf>", b"</RtrRsnInf><ChrgBr>SLEV</ChrgBr>", 1)

    with pytest.raises(PacsValidationError) as caught:
        validate(misplaced)

    assert "ChrgBr" in caught.value.errors[0]
    assert isinstance(caught.value, PacsError)


@pytest.mark.parametrize("xml", [b"not xml", b"<Document/>", b'<Document xmlns="urn:example:other"/>',
                                 b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08"/>'])
def test_what_is_not_a_known_pacs_document_is_one_error(xml):
    [error] = schema_errors(xml)
    assert error.startswith(("not XML", "not a pacs message"))
    with pytest.raises(PacsValidationError):
        validate(xml)


def test_a_document_missing_a_mandatory_element_is_refused():
    xml = credit_transfer_xml().replace(b"<NbOfTxs>1</NbOfTxs>", b"", 1)
    assert schema_errors(xml)
