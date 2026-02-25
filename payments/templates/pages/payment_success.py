# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe

no_cache = True


def get_context(context):
	if frappe.local.form_dict.redirect_to:
		frappe.local.flags.redirect_location = frappe.local.form_dict.redirect_to
		raise frappe.Redirect
		
	doc = frappe.get_doc(frappe.local.form_dict.doctype, frappe.local.form_dict.docname)

	context.payment_message = ""
	if hasattr(doc, "get_payment_success_message"):
		context.payment_message = doc.get_payment_success_message()
