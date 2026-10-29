# Copyright (c) 2026, TFSS and Contributors
# See license.txt

import hashlib
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings import (
	format_amount,
	generate_request_hash,
	generate_response_hash,
)

MODULE = "payments.payment_gateways.doctype.easebuzz_settings.easebuzz_settings"
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []

SALT = "TESTSALT"
PARAMS = {
	"key": "TESTKEY",
	"txnid": "PR-0001-1",
	"amount": "1500.00",
	"productinfo": "Application Fee",
	"firstname": "Nuran",
	"email": "nuran@example.com",
	"udf1": "SLCM Payment Request",
	"udf2": "PR-0001",
}


def _sha512(text):
	return hashlib.sha512(text.encode("utf-8")).hexdigest()


class IntegrationTestEasebuzzSettings(IntegrationTestCase):
	def test_format_amount(self):
		self.assertEqual(format_amount(1500), "1500.00")
		self.assertEqual(format_amount("99.5"), "99.50")
		self.assertEqual(format_amount(99.999), "100.00")
		self.assertRaises(frappe.ValidationError, format_amount, 0)
		self.assertRaises(frappe.ValidationError, format_amount, -5)

	def test_request_hash_sequence(self):
		expected = _sha512(
			"TESTKEY|PR-0001-1|1500.00|Application Fee|Nuran|nuran@example.com"
			"|SLCM Payment Request|PR-0001||||||||" + "|TESTSALT"
		)
		self.assertEqual(generate_request_hash(PARAMS, SALT), expected)

	def test_response_hash_sequence(self):
		params = {**PARAMS, "status": "success"}
		expected = _sha512(
			"TESTSALT|success|||||||||PR-0001|SLCM Payment Request"
			"|nuran@example.com|Nuran|Application Fee|1500.00|PR-0001-1|TESTKEY"
		)
		self.assertEqual(generate_response_hash(params, SALT), expected)

	def test_response_hash_detects_tampering(self):
		params = {**PARAMS, "status": "success"}
		original = generate_response_hash(params, SALT)
		self.assertNotEqual(original, generate_response_hash({**params, "amount": "1.00"}, SALT))
		self.assertNotEqual(original, generate_response_hash({**params, "status": "failure"}, SALT))

	def test_disabled_settings_do_not_create_gateway(self):
		settings = frappe.get_single("Easebuzz Settings")
		settings.enabled = 0
		settings.save()
		self.assertRaises(frappe.ValidationError, settings.ensure_enabled)


class IntegrationTestEasebuzzController(IntegrationTestCase):
	def setUp(self):
		self.settings = frappe.get_single("Easebuzz Settings")
		self.settings.update({"enabled": 1, "environment": "Test", "merchant_key": "TESTKEY", "salt": f" {SALT} "})
		with patch(f"{MODULE}.create_payment_gateway"), patch(f"{MODULE}.call_hook_method"):
			self.settings.save()

	def tearDown(self):
		frappe.db.rollback()

	def _initiate(self, **overrides):
		kwargs = {
			"txnid": "PR-0001-1",
			"amount": 1500,
			"productinfo": "Application Fee",
			"firstname": "Nuran",
			"email": "nuran@example.com",
			"phone": "9999999999",
			"surl": "https://example.com/s",
			"furl": "https://example.com/f",
			**overrides,
		}
		return self.settings.initiate_payment(**kwargs)

	def test_salt_is_stripped(self):
		self.assertEqual(self.settings.get_salt(), SALT)

	@patch(f"{MODULE}.requests.post")
	def test_initiate_sends_hash_and_returns_access_key(self, post):
		post.return_value = _response({"status": 1, "data": "abc123ACCESS"})
		self.assertEqual(self._initiate(), "abc123ACCESS")

		sent = post.call_args.kwargs["data"]
		self.assertEqual(sent["amount"], "1500.00")
		self.assertEqual(sent["hash"], generate_request_hash(sent, SALT))
		self.assertTrue(post.call_args.kwargs["timeout"])

	@patch(f"{MODULE}.requests.post")
	def test_initiate_rejects_bad_input(self, post):
		self.assertRaises(frappe.ValidationError, self._initiate, txnid="PR 0001")
		self.assertRaises(frappe.ValidationError, self._initiate, phone="")
		self.assertRaises(frappe.ValidationError, self._initiate, firstname="Nu|ran")
		self.assertRaises(frappe.ValidationError, self._initiate, udf1="a|b")
		self.assertRaises(frappe.ValidationError, self._initiate, udf11="x")
		post.assert_not_called()

	@patch(f"{MODULE}.requests.post")
	def test_initiate_failure_logs_no_customer_data(self, post):
		post.return_value = _response({"status": 0, "error_desc": "Invalid amount", "data": "nuran@example.com"})
		self.assertRaises(frappe.ValidationError, self._initiate)

		log = frappe.get_last_doc("Error Log", filters={"method": "Easebuzz Initiate Payment Failed"})
		self.assertIn("Invalid amount", log.error)
		self.assertNotIn("nuran@example.com", log.error)
		self.assertNotIn("9999999999", log.error)

	@patch(f"{MODULE}.requests.post")
	def test_initiate_rejects_malformed_access_key(self, post):
		post.return_value = _response({"status": 1, "data": "../evil?x=1"})
		self.assertRaises(frappe.ValidationError, self._initiate)
		self.assertRaises(frappe.ValidationError, self.settings.get_checkout_url, "../evil")

	@patch(f"{MODULE}.requests.post", side_effect=requests.Timeout())
	def test_network_error_is_handled(self, post):
		self.assertRaises(frappe.ValidationError, self._initiate)

	def test_verify_response_hash(self):
		params = {**PARAMS, "status": "success"}
		params["hash"] = generate_response_hash(params, SALT)
		self.assertTrue(self.settings.verify_response_hash(params))

		for tampered in (
			{**params, "amount": "1.00"},
			{**params, "key": "OTHERKEY"},
			{**params, "hash": ""},
			{**params, "hash": "é" * 128},
		):
			self.assertRaises(frappe.PermissionError, self.settings.verify_response_hash, tampered)

	def test_verify_works_when_disabled(self):
		self.settings.enabled = 0
		params = {**PARAMS, "status": "success"}
		params["hash"] = generate_response_hash(params, SALT)
		self.assertTrue(self.settings.verify_response_hash(params))

	@patch(f"{MODULE}.requests.post")
	def test_retrieve_transaction(self, post):
		post.return_value = _response({"status": True, "msg": []})
		self.settings.retrieve_transaction("PR-0001-1")
		self.assertEqual(post.call_args.kwargs["json"]["hash"], _sha512(f"TESTKEY|PR-0001-1|{SALT}"))
		self.assertRaises(frappe.ValidationError, self.settings.retrieve_transaction, "PR|1")


def _response(payload):
	response = MagicMock()
	response.json.return_value = payload
	return response
