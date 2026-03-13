# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe.utils import flt, fmt_money
from frappe.utils.pdf import get_pdf

no_cache = True


def _get_receipt_from_token(doctype: str, docname: str, token: str):
	if not (doctype and docname and token):
		return None

	if not frappe.db.exists("Integration Request", token):
		return None

	integration = frappe.get_doc("Integration Request", token)
	if integration.reference_doctype != doctype or integration.reference_docname != docname:
		return None

	if integration.status not in ("Completed", "Authorized", "Verified"):
		return None

	data = frappe.parse_json(integration.data) or {}
	currency = data.get("currency") or ""
	amount = flt(data.get("amount"))
	transaction_id = data.get("razorpay_payment_id") or ""
	payment_status = integration.status
	paid_on = integration.modified

	payer_name = data.get("payer_name") or ""
	payer_email = data.get("payer_email") or ""
	reference_no = docname

	# FLE: show candidate details from the application (safe because token is required)
	if doctype == "Foundations for a Legal Education":
		row = frappe.db.get_value(
			doctype,
			docname,
			["candidate_name", "email_address", "payment_status", "paid_amount", "payment_id", "modified"],
			as_dict=True,
		)
		if row:
			payer_name = row.get("candidate_name") or payer_name
			payer_email = row.get("email_address") or payer_email
			payment_status = row.get("payment_status") or payment_status
			amount = flt(row.get("paid_amount")) or amount
			transaction_id = row.get("payment_id") or transaction_id
			paid_on = row.get("modified") or paid_on

	return {
		"reference_doctype": doctype,
		"reference_docname": docname,
		"reference_no": reference_no,
		"name": payer_name,
		"email": payer_email,
		"payment_status": payment_status,
		"amount": amount,
		"currency": currency,
		"amount_formatted": fmt_money(amount, currency=currency) if currency else str(amount),
		"transaction_id": transaction_id,
		"paid_on": paid_on,
		"token": token,
	}


def get_context(context):
	# Keep user on this page; show a "Continue" button instead.
	context.redirect_to = frappe.local.form_dict.get("redirect_to")

	doctype = frappe.local.form_dict.get("doctype")
	docname = frappe.local.form_dict.get("docname")
	token = frappe.local.form_dict.get("token")

	receipt = _get_receipt_from_token(doctype, docname, token)
	context.receipt = receipt

	context.payment_message = ""
	if receipt and receipt.get("payment_status"):
		context.payment_message = frappe._("Your payment was successfully accepted.")


@frappe.whitelist(allow_guest=True)
def download_receipt_pdf(doctype: str = None, docname: str = None, token: str = None):
	receipt = _get_receipt_from_token(doctype, docname, token)
	if not receipt:
		frappe.throw("Invalid receipt reference.", frappe.PermissionError)

	def esc(v):
		return frappe.utils.escape_html(str(v or ""))

	logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")

	html = f"""
		<html>
		<head>
			<meta charset="utf-8" />
			<style>
				body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 12px; color: #111827; }}
				.h1 {{ font-size: 18px; font-weight: 700; margin: 12px 0 12px 0; }}
				.sub {{ color: #4b5563; margin: 0 0 12px 0; }}
				table {{ width: 100%; border-collapse: collapse; }}
				td {{ padding: 10px 12px; border: 1px solid #E5E7EB; vertical-align: top; }}
				td.k {{ width: 35%; background: #F9FAFB; font-weight: 600; }}
				
				/* Header Styles */
				table.header-table {{ border: none; margin-bottom: 20px; border-bottom: 2px solid #a81119; padding-bottom: 10px; }}
				table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
				.header-title-container {{ text-align: center; color: #a81119; font-family: "Merriweather", serif; }}
				.university-name {{ font-size: 16px; font-weight: bold; margin: 0; }}
				.department-name {{ font-size: 14px; font-weight: bold; margin: 5px 0 0 0; }}
			</style>
		</head>
		<body>
			<table class="header-table">
				<tr>
					<td style="width: 80px;">
						<img src="{esc(logo_url)}" style="width: 60px; height: auto;" />
					</td>
					<td class="header-title-container">
						<div class="university-name">National Law School of India University, Bengaluru</div>
						<div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
					</td>
					<td style="width: 80px;"></td> <!-- Spacer for center alignment -->
				</tr>
			</table>
			<div class="h1">Payment Receipt</div>
			<p class="sub">Reference: {esc(receipt.get("reference_no"))}</p>
			<table>
				<tr><td class="k">Name</td><td>{esc(receipt.get("name"))}</td></tr>
				<tr><td class="k">Email</td><td>{esc(receipt.get("email"))}</td></tr>
				<tr><td class="k">Payment Status</td><td>{esc(receipt.get("payment_status"))}</td></tr>
				<tr><td class="k">Amount</td><td>{esc(receipt.get("amount_formatted"))}</td></tr>
				<tr><td class="k">Transaction ID</td><td>{esc(receipt.get("transaction_id"))}</td></tr>
				<tr><td class="k">Reference</td><td>{esc(receipt.get("reference_no"))}</td></tr>
				<tr><td class="k">Date</td><td>{esc(receipt.get("paid_on"))}</td></tr>
			</table>
		</body>
		</html>
	"""

	pdf = get_pdf(html)
	frappe.local.response.filename = f"Receipt-{receipt.get('reference_no')}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"
