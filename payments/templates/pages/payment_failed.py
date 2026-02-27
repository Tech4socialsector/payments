import json

import frappe


def get_context(context):
	"""Handle payment failure finalization and redirect target."""
	token = frappe.local.form_dict.get("token")
	context.redirect_to = frappe.local.form_dict.get("redirect_to") or "/"

	if not token or not frappe.db.exists("Integration Request", token):
		return

	# Mark Integration Request as failed (if not already)
	frappe.db.set_value("Integration Request", token, "status", "Failed")

	try:
		integration = frappe.get_doc("Integration Request", token)
		data = json.loads(integration.data or "{}")
		reference_doctype = data.get("reference_doctype")
		reference_docname = data.get("reference_docname")

		if reference_doctype and reference_docname and frappe.db.exists(reference_doctype, reference_docname):
			# Special handling for FLE application
			if reference_doctype == "Foundations for a Legal Education":
				current = frappe.db.get_value(reference_doctype, reference_docname, "payment_status")
				if current != "Paid":
					frappe.db.set_value(reference_doctype, reference_docname, "payment_status", "Payment Failed")

				# Try to find the public Web Form route for this doctype so the user can retry payment
				webform_route = frappe.db.get_value(
					"Web Form",
					{"doc_type": reference_doctype, "published": 1},
					"route",
				)
				if webform_route:
					context.redirect_to = f"/{webform_route}"
	finally:
		frappe.db.commit()

