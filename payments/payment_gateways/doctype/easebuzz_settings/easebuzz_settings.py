# Copyright (c) 2026, TFSS and contributors
# License: MIT. See LICENSE

"""
Easebuzz Payment Gateway Integration.

Amounts are sent in INR with two decimal places (e.g. "1500.00").

Payment flow:
1. Initiate a payment and obtain an access key.
2. Redirect the customer to Easebuzz checkout.
3. Verify callback/webhook hashes before processing payments.
4. Retrieve transaction details for reconciliation.

Never log access keys, credentials, or raw payment responses.
"""

import hashlib  # Generates SHA-512 hashes.
import hmac  # Compares values securely.
import re  # Validates transaction IDs and access keys.

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import call_hook_method, flt

from payments.utils import create_payment_gateway


# Payment and transaction API URLs for test and live environments.
BASE_URLS = {
    "Test": {
        "pay": "https://testpay.easebuzz.in",
        "dashboard": "https://testdashboard.easebuzz.in",
    },
    "Production": {
        "pay": "https://pay.easebuzz.in",
        "dashboard": "https://dashboard.easebuzz.in",
    },
}

# Easebuzz supports ten optional user-defined fields.
UDF_FIELDS = tuple(f"udf{i}" for i in range(1, 11))

# Field order must match the Easebuzz request hash specification.
REQUEST_HASH_FIELDS = (
    "key",
    "txnid",
    "amount",
    "productinfo",
    "firstname",
    "email",
    *UDF_FIELDS,
)

# Field order must match the Easebuzz response hash specification.
RESPONSE_HASH_FIELDS = (
    *reversed(UDF_FIELDS),
    "email",
    "firstname",
    "productinfo",
    "amount",
    "txnid",
    "key",
)

# Allow only letters, numbers, underscores, and hyphens in transaction IDs.
TXNID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")

# Restrict access keys to alphanumeric characters.
ACCESS_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]+$")

# Required fields for initiating a payment.
REQUIRED_FIELDS = (
    "productinfo",
    "firstname",
    "email",
    "phone",
    "surl",
    "furl",
)

# Connection timeout: 5 seconds; response timeout: 30 seconds.
REQUEST_TIMEOUT = (5, 30)


def format_amount(amount):
    """Validate the amount and format it in rupees with two decimal places."""
    amount = flt(amount, 2)

    if amount <= 0:
        frappe.throw(_("Easebuzz amount must be greater than zero"))

    return f"{amount:.2f}"


def sha512(text):
    """Return the lowercase hexadecimal SHA-512 hash of a string."""
    return hashlib.sha512(text.encode("utf-8")).hexdigest().lower()


def generate_request_hash(params, salt):
    """Generate the hash required to initiate a payment."""
    values = [str(params.get(field) or "") for field in REQUEST_HASH_FIELDS]
    return sha512("|".join([*values, salt]))


def generate_response_hash(params, salt):
    """Generate the expected hash for a callback or webhook response."""
    values = [str(params.get(field) or "") for field in RESPONSE_HASH_FIELDS]
    return sha512("|".join([salt, str(params.get("status") or ""), *values]))


def safe_equals(a, b):
    """Compare values securely, including strings containing non-ASCII characters."""
    return hmac.compare_digest(
        str(a or "").encode("utf-8"),
        str(b or "").encode("utf-8"),
    )


def validate_txnid(txnid):
    """Validate and return a transaction ID in the supported format."""
    txnid = (txnid or "").strip()

    if not TXNID_PATTERN.match(txnid):
        frappe.throw(
            _("Invalid Easebuzz txnid '{0}'. Use only letters, digits, - and _").format(
                txnid
            )
        )

    return txnid


def post_to_easebuzz(url, action, **kwargs):
    """Send a timed API request and log failures without sensitive payloads."""
    try:
        response = requests.post(
            url,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        # Log only the URL and exception type, never request or response data.
        frappe.log_error(
            title=f"Easebuzz {action} Request Failed",
            message=f"url: {url}\nerror: {type(e).__name__}",
        )
        frappe.throw(_("Could not reach Easebuzz. Please try again."))


class EasebuzzSettings(Document):
    # Easebuzz transactions are supported only in Indian Rupees.
    supported_currencies = ("INR",)

    def validate(self):
        """Clean credentials and register the gateway when enabled."""
        if self.merchant_key:
            self.merchant_key = self.merchant_key.strip()

        # Avoid modifying Frappe's masked placeholder for an unchanged password.
        if self.salt and not self.is_dummy_password(self.salt):
            self.salt = self.salt.strip()

        if self.enabled:
            create_payment_gateway("Easebuzz")
            call_hook_method("payment_gateway_enabled", gateway="Easebuzz")

    def validate_transaction_currency(self, currency):
        """Reject transactions in unsupported currencies."""
        if currency not in self.supported_currencies:
            frappe.throw(
                _(
                    "Please select another payment method. Easebuzz does not "
                    "support transactions in currency '{0}'"
                ).format(currency)
            )

    def get_base_url(self, kind="pay"):
        """Return the endpoint for the configured environment and API type."""
        return BASE_URLS[self.environment or "Test"][kind]

    def get_salt(self):
        """Retrieve the stored Salt used to generate and verify hashes."""
        salt = self.get_password(
            fieldname="salt",
            raise_exception=False,
        )

        if not self.merchant_key or not salt:
            frappe.throw(
                _("Easebuzz Merchant Key and Salt are not configured")
            )

        return salt

    def ensure_enabled(self):
        """Stop payment initiation when the gateway is disabled."""
        if not self.enabled:
            frappe.throw(_("Easebuzz is not enabled"))

    def initiate_payment(
        self,
        txnid,
        amount,
        productinfo,
        firstname,
        email,
        phone,
        surl,
        furl,
        **udfs,
    ):
        """Create a payment request and return the Easebuzz access key."""
        self.ensure_enabled()

        # Validate the transaction ID before sending the request.
        txnid = validate_txnid(txnid)

        # Reject unsupported user-defined fields.
        unknown = set(udfs) - set(UDF_FIELDS)
        if unknown:
            frappe.throw(
                _("Unknown Easebuzz parameters: {0}").format(
                    ", ".join(sorted(unknown))
                )
            )

        # Build the request with all ten UDF fields.
        params = {
            "key": self.merchant_key,
            "txnid": txnid,
            "amount": format_amount(amount),
            "productinfo": productinfo,
            "firstname": firstname,
            "email": email,
            "phone": phone,
            "surl": surl,
            "furl": furl,
            **{field: udfs.get(field) or "" for field in UDF_FIELDS},
        }

        # Ensure all required customer, product, and callback details are present.
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(params[field] or "").strip()
        ]
        if missing:
            frappe.throw(
                _("Missing Easebuzz parameters: {0}").format(
                    ", ".join(missing)
                )
            )

        # Prevent values from changing the field boundaries in the hash string.
        piped = [
            field
            for field in REQUEST_HASH_FIELDS
            if "|" in str(params[field] or "")
        ]
        if piped:
            frappe.throw(
                _("Easebuzz parameters cannot contain '|': {0}").format(
                    ", ".join(piped)
                )
            )

        # Authenticate the request using the configured Salt.
        params["hash"] = generate_request_hash(
            params,
            self.get_salt(),
        )

        # Submit the payment details to Easebuzz.
        response = post_to_easebuzz(
            f"{self.get_base_url()}/payment/initiateLink",
            "Initiate",
            data=params,
        )

        # Stop if Easebuzz does not return a successful response and access key.
        if (
            not isinstance(response, dict)
            or response.get("status") != 1
            or not response.get("data")
        ):
            # Log only a limited error message, not the complete API response.
            error = (
                response.get("error_desc")
                if isinstance(response, dict)
                else None
            )
            frappe.log_error(
                title="Easebuzz Initiate Payment Failed",
                message=f"txnid: {txnid}\nerror: {str(error or 'Unknown error')[:500]}",
            )
            frappe.throw(
                _("Could not start Easebuzz payment. Please try again or contact support.")
            )

        # Validate the returned access key before using it in a checkout URL.
        access_key = str(response["data"])
        if not ACCESS_KEY_PATTERN.match(access_key):
            frappe.log_error(
                title="Easebuzz Initiate Payment Failed",
                message=f"txnid: {txnid}\nerror: malformed access key",
            )
            frappe.throw(
                _("Could not start Easebuzz payment. Please try again or contact support.")
            )

        return access_key

    def get_checkout_url(self, access_key):
        """Build the checkout URL after validating the access key."""
        if not ACCESS_KEY_PATTERN.match(str(access_key or "")):
            frappe.throw(_("Invalid Easebuzz access key"))

        return f"{self.get_base_url()}/pay/{access_key}"

    def verify_response_hash(self, params):
        """Verify callback/webhook authenticity and reject modified responses.

        This verification does not require the gateway to remain enabled,
        allowing payments initiated before disabling to complete.
        """
        salt = self.get_salt()
        received = str(params.get("hash") or "").lower()

        # Confirm that the response belongs to the configured merchant.
        key_matches = safe_equals(
            params.get("key"),
            self.merchant_key,
        )

        # Recalculate the expected hash from the returned transaction fields.
        expected = generate_response_hash(params, salt)

        # Reject missing hashes, incorrect merchant keys, or mismatched hashes.
        if (
            not received
            or not key_matches
            or not safe_equals(expected, received)
        ):
            frappe.throw(
                _("Easebuzz Hash Verification Failed"),
                exc=frappe.PermissionError,
            )

        return True

    def retrieve_transaction(self, txnid):
        """Retrieve a transaction's current status for reconciliation.

        The response may contain customer data; never log it in full.
        """
        # Validate the transaction ID before querying the gateway.
        txnid = validate_txnid(txnid)
        salt = self.get_salt()

        params = {
            "key": self.merchant_key,
            "txnid": txnid,
        }

        # Generate the authentication hash required by the retrieval API.
        params["hash"] = sha512(
            "|".join([self.merchant_key, txnid, salt])
        )

        # Fetch the transaction details from the Easebuzz dashboard API.
        return post_to_easebuzz(
            f"{self.get_base_url('dashboard')}/transaction/v2.1/retrieve",
            "Retrieve",
            json=params,
            headers={"Accept": "application/json"},
        )

    @frappe.whitelist()
    def clear(self):
        """Remove gateway credentials and disable Easebuzz."""
        self.merchant_key = self.salt = None
        self.enabled = 0
        self.redirect_to = None

        # Allow saving the settings after mandatory credentials are cleared.
        self.flags.ignore_mandatory = True
        self.save()