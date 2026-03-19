# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import os

import frappe
from frappe.utils import flt, fmt_money
from frappe.utils.pdf import get_pdf

no_cache = True


def _get_photo_src(photo_url):
	"""Return a base64 data URI for a Frappe file so wkhtmltopdf never makes HTTP requests."""
	if not photo_url:
		return None
	try:
		import base64, mimetypes

		if photo_url.startswith("/private/files/"):
			file_path = os.path.abspath(frappe.get_site_path("private", "files", photo_url[len("/private/files/"):]))
		elif photo_url.startswith("/files/"):
			file_path = os.path.abspath(frappe.get_site_path("public", "files", photo_url[len("/files/"):]))
		else:
			return None

		if not os.path.exists(file_path):
			return None
		with open(file_path, "rb") as f:
			data = f.read()
		mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"
		b64 = base64.b64encode(data).decode("utf-8")
		return f"data:{mime_type};base64,{b64}"
	except Exception:
		return None


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
	candidate_photo = ""

	# FLE: show candidate details from the application (safe because token is required)
	if doctype == "Foundations for a Legal Education":
		row = frappe.db.get_value(
			doctype,
			docname,
			["candidate_name", "email_address", "payment_status", "paid_amount", "payment_id", "modified", "candidate_photo"],
			as_dict=True,
		)
		if row:
			payer_name = row.get("candidate_name") or payer_name
			payer_email = row.get("email_address") or payer_email
			payment_status = row.get("payment_status") or payment_status
			amount = flt(row.get("paid_amount")) or amount
			transaction_id = row.get("payment_id") or transaction_id
			paid_on = row.get("modified") or paid_on
			candidate_photo = row.get("candidate_photo") or ""

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
		"candidate_photo": candidate_photo,
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

	photo_src = _get_photo_src(receipt.get("candidate_photo"))
	if photo_src:
		photo_td = f'<td style="width: 100px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 90px; height: 110px; object-fit: cover; border: 1px solid #E5E7EB;" /></td>'
	else:
		photo_td = '<td style="width: 100px;"></td>'

	html = f"""
		<html>
		<head>
			<meta charset="utf-8" />
			<link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
			<style>
				body {{ font-family: "Merriweather", serif; font-size: 12px; color: #111827; }}
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
					{photo_td}
				</tr>
			</table>
			<div class="h1">Payment receipt</div>
			<p class="sub">Reference: {esc(receipt.get("reference_no"))}</p>
			<table>
				<tr><td class="k">Name</td><td>{esc(receipt.get("name"))}</td></tr>
				<tr><td class="k">Email</td><td>{esc(receipt.get("email"))}</td></tr>
				<tr><td class="k">Payment status</td><td>{esc(receipt.get("payment_status"))}</td></tr>
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


@frappe.whitelist(allow_guest=True)
def download_application_pdf(doctype: str = None, docname: str = None, token: str = None):
	receipt = _get_receipt_from_token(doctype, docname, token)
	if not receipt:
		frappe.throw("Invalid receipt reference.", frappe.PermissionError)

	if doctype != "Foundations for a Legal Education":
		frappe.throw("Application download is only available for FLE documents.", frappe.ValidationError)

	doc = frappe.get_doc("Foundations for a Legal Education", docname)

	def esc(v):
		return frappe.utils.escape_html(str(v or ""))

	def row(label, value):
		return f'<tr><td class="k">{esc(label)}</td><td>{esc(value)}</td></tr>'

	def sec(title):
		return f'<tr><td colspan="2" class="sec-head">{esc(title)}</td></tr>'

	logo_url = frappe.utils.get_url("/files/nlsiu-logo.jpg")

	photo_src = _get_photo_src(doc.candidate_photo)
	if photo_src:
		photo_td = f'<td style="width: 110px; text-align: right; vertical-align: middle;"><img src="{photo_src}" style="width: 100px; height: 125px; object-fit: cover; border: 1px solid #E5E7EB;" /></td>'
	else:
		photo_td = '<td style="width: 110px;"></td>'

	year_of_passing = doc.year_of_passing or ""
	if year_of_passing == "Prior to 2016" and doc.please_specify_the_year_of_passing:
		year_of_passing = f"Prior to 2016 ({doc.please_specify_the_year_of_passing})"

	occupation = doc.candidate_current_occupation or ""
	if occupation == "Other" and doc.if_other4:
		occupation = f"Other ({doc.if_other4})"

	state = doc.candidates_state or ""
	if state == "Other" and doc.if_other3:
		state = f"Other ({doc.if_other3})"

	board = doc.latest_board_attended or ""
	if board == "Other" and doc.if_others2:
		board = f"Other ({doc.if_others2})"

	exam = doc.last_class_attended or ""
	if exam == "Other" and doc.if_others1:
		exam = f"Other ({doc.if_others1})"

	where_heard = doc.where_did_you_hear or ""
	if where_heard == "Other" and doc.if_others_mention_here:
		where_heard = f"Other ({doc.if_others_mention_here})"

	html = f"""
		<html>
		<head>
			<meta charset="utf-8" />
			<link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap" rel="stylesheet" />
			<style>
				body {{ font-family: "Merriweather", serif; font-size: 11px; color: #111827; }}
				table.header-table {{ border: none; margin-bottom: 16px; border-bottom: 2px solid #a81119; padding-bottom: 8px; width: 100%; border-collapse: collapse; }}
				table.header-table td {{ border: none; padding: 0; vertical-align: middle; }}
				.header-title-container {{ text-align: center; color: #a81119; }}
				.university-name {{ font-size: 15px; font-weight: bold; margin: 0; }}
				.department-name {{ font-size: 12px; font-weight: bold; margin: 4px 0 0 0; }}
				.app-ref {{ font-size: 11px; margin: 4px 0 0 0; color: #374151; }}
				table.main {{ width: 100%; border-collapse: collapse; margin-bottom: 0; }}
				table.main td {{ padding: 7px 10px; border: 1px solid #E5E7EB; vertical-align: top; }}
				table.main td.k {{ width: 38%; background: #F9FAFB; font-weight: 600; }}
				table.main td.sec-head {{ background: #a81119; color: #fff; font-weight: 700; font-size: 11px; padding: 5px 10px; }}
			</style>
		</head>
		<body>
			<table class="header-table">
				<tr>
					<td style="width: 75px;">
						<img src="{esc(logo_url)}" style="width: 55px; height: auto;" />
					</td>
					<td class="header-title-container">
						<div class="university-name">National Law School of India University, Bengaluru</div>
						<div class="department-name">Foundations for a Legal Education Certificate Course (FLE)</div>
						<div class="app-ref">Application form — {esc(doc.name)}</div>
					</td>
					{photo_td}
				</tr>
			</table>
			<table class="main">
				{sec("Candidate details")}
				{row("Application number", doc.name)}
				{row("Submission date", doc.timestamp)}
				{row("Name on certificate", doc.candidate_name)}
				{row("Email address", doc.email_address)}
				{row("Current occupation", occupation)}
				{row("Gender", doc.candidate_gender)}
				{row("Date of birth", doc.candidate_dob)}
				{row("Nationality", doc.candidate_nationality)}
				{row("Country of residence", doc.country_of_residence)}
				{row("State", state)}
				{row("City", doc.city)}
				{row("Address line 1", doc.address_line_1)}
				{row("Pincode", doc.pincode)}
				{row("Contact number", doc.candidate_contact_number)}
				{row("Where did you hear about FLE?", where_heard)}

				{sec("Educational background")}
				{row("Last examination attended", exam)}
				{row("Latest board", board)}
				{row("Year of passing", year_of_passing)}
				{row("Last institution attended", doc.last_institution_attended)}

				{sec("Parent / guardian details")}
				{row("Relationship with candidate", doc.relationship_with_candidate)}
				{row("Parent's name", doc.parent_name)}
				{row("Parent's contact number", doc.parent_contact_number)}
				{row("Parent's email address", doc.parent_email_address)}
				{row("Parent's occupation", doc.parent_occupation)}

				{sec("Payment details")}
				{row("Payment status", doc.payment_status)}
				{row("Amount paid", doc.paid_amount)}
				{row("Payment ID", doc.payment_id)}

				{sec("Application status")}
				{row("Enrollment status", doc.enrollment_status)}
				{row("Declaration consent", "Yes" if doc.declaration_consent else "No")}
			</table>
		</body>
		</html>
	"""

	pdf = get_pdf(html)
	frappe.local.response.filename = f"FLE-Application-{docname}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"
