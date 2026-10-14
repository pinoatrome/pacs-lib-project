"""The documents `pacs.testing` makes: valid, and what the test asked for."""
from decimal import Decimal

import pytest

from pacs import parse_pacs002, parse_pacs004, parse_pacs008, parse_pacs028, schema_errors
from pacs.testing import (
    credit_transfer_xml,
    payment_return_xml,
    rejected_report_xml,
    status_report_xml,
    status_request_xml,
)


@pytest.mark.parametrize("make", [
    lambda: credit_transfer_xml(),
    lambda: credit_transfer_xml(creditor="IT60X0542811101000000654321", remittance_info="Order 7", creditor_agent_bic="BCITITMMXXX"),
    lambda: credit_transfer_xml(debtor_agent_bic=None),
    lambda: status_report_xml(original_message_id="PSP-0001"),
    lambda: status_report_xml(original_message_id="PSP-0001", end_to_end_ids=["A", "B"], status="PDNG"),
    lambda: rejected_report_xml(original_message_id="PSP-0001", additional_info="Insufficient funds"),
    lambda: status_request_xml(original_message_id="PSP-0001"),
    lambda: status_request_xml(original_message_id="PSP-0001", end_to_end_ids=["A", "B"],
                               original_message_name_id="pacs.004.001.09"),
    lambda: payment_return_xml(original_message_id="PSP-0001"),
    lambda: payment_return_xml(original_message_id="PSP-0001", original_debtor="IT60X0542811101000000654321", reason_code="CUST"),
])
def test_every_sample_is_valid_against_the_schema(make):
    assert schema_errors(make()) == []


def test_a_credit_transfer_is_what_was_asked():
    [tx] = parse_pacs008(credit_transfer_xml(
        message_id="M-1", end_to_end_id="E-1", amount="45.50", debtor="DEAN-A", creditor="IT60X0542811101000000654321",
        remittance_info="Order 7")).transactions
    assert (tx.end_to_end_id, tx.amount, tx.debtor.other_id, tx.creditor.iban, tx.remittance_info) == (
        "E-1", Decimal("45.50"), "DEAN-A", "IT60X0542811101000000654321", "Order 7")


def test_a_settled_report_is_the_default():
    report = parse_pacs002(status_report_xml(original_message_id="PSP-0001"))
    assert report.original_message_id == "PSP-0001"
    assert report.status_of("TEST-E2E-0001") == "ACSC"


def test_a_rejected_report_carries_its_reason():
    [status] = parse_pacs002(rejected_report_xml(original_message_id="PSP-0001", reason_code="AC06")).transactions
    assert (status.status, status.reason_code) == ("RJCT", "AC06")


def test_a_status_request_names_the_transactions():
    request = parse_pacs028(status_request_xml(original_message_id="PSP-0001", end_to_end_ids=["A", "B"]))
    assert request.original_end_to_end_ids == ["A", "B"]


def test_a_return_is_what_was_asked():
    [tx] = parse_pacs004(payment_return_xml(original_message_id="PSP-0001", amount="10.00", reason_code="DUPL")).transactions
    assert (tx.original_message_id, tx.returned_amount, tx.reason_code) == ("PSP-0001", Decimal("10.00"), "DUPL")
