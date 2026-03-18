# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
import json


def get_context(context):
	token = frappe.local.form_dict.get("token")

	if not token:
		return

	if not frappe.db.exists("Integration Request", token):
		return

	# Mark Integration Request as cancelled
	frappe.db.set_value("Integration Request", token, "status", "Cancelled")

	try:
		# Update linked document status when applicable (e.g. FLE application)
		integration = frappe.get_doc("Integration Request", token)
		data = json.loads(integration.data or "{}")
		reference_doctype = data.get("reference_doctype")
		reference_docname = data.get("reference_docname")

		if reference_doctype and reference_docname and frappe.db.exists(reference_doctype, reference_docname):
			if reference_doctype == "Foundations for a Legal Education":
				current = frappe.db.get_value(reference_doctype, reference_docname, "payment_status")
				if current not in ("Paid", "Cancelled"):
					frappe.db.set_value(reference_doctype, reference_docname, "payment_status", "Cancelled")

				# Redirect to the web form in edit mode so the user can retry
				webform_route = frappe.db.get_value(
					"Web Form",
					{"doc_type": reference_doctype, "published": 1},
					"route",
				)
				if webform_route:
					context.redirect_to = f"/{webform_route}/{reference_docname}"
	finally:
		frappe.db.commit()
