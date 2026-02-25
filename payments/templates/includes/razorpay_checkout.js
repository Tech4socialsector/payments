$(document).ready(function () {
	(function (e) {
		var options = {
			"key": "{{ api_key }}",
			"amount": cint({{ amount }} * 100), // 2000 paise = INR 20
		"currency": "{{ currency }}",
			"name": "{{ title }}",
				"description": "{{ description }}",
					"subscription_id": "{{ subscription_id }}",
						"order_id": "{{ order_id }}",
							"handler": function (response) {
								razorpay.make_payment_log(response, options, "{{ reference_doctype }}", "{{ reference_docname }}", "{{ token }}");
							},
	"prefill": {
		"name": "{{ payer_name }}",
			"email": "{{ payer_email }}"
	},
	// prettier-ignore
	"notes": {{ frappe.form_dict | json }}
};

var rzp = new Razorpay(options);
rzp.open();
		//	e.preventDefault();
	}) ();
})

frappe.provide('razorpay');

razorpay.make_payment_log = function (response, options, doctype, docname, token) {
	$('.razorpay-loading').addClass('hidden');
	$('.razorpay-confirming').removeClass('hidden');

	frappe.call({
		method: "payments.templates.pages.razorpay_checkout.make_payment",
		freeze: true,
		headers: { "X-Requested-With": "XMLHttpRequest" },
		args: {
			"razorpay_payment_id": response.razorpay_payment_id,
			"options": options,
			"reference_doctype": doctype,
			"reference_docname": docname,
			"token": token
		},
		callback: function (r) {
			if (r.message && r.message.status == 200) {
				let final_url = r.message.redirect_to;
				// If Frappe nested our custom URL as a query parameter (e.g. payment-success?doctype=...&redirect_to=/fle-success-page...)
				let url_obj = new URL(final_url, window.location.origin);
				if (url_obj.searchParams.has('redirect_to')) {
					final_url = url_obj.searchParams.get('redirect_to');
				}
				window.location.href = final_url;
			}
			else if (r.message && ([401, 400, 500].indexOf(r.message.status) > -1)) {
				let final_url = r.message.redirect_to;
				let url_obj = new URL(final_url, window.location.origin);
				if (url_obj.searchParams.has('redirect_to')) {
					final_url = url_obj.searchParams.get('redirect_to');
				}
				window.location.href = final_url;
			}
		}
	})
}
