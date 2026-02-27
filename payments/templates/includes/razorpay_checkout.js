$(document).ready(function () {
	(function (e) {
		window.__razorpay_flow_cancelled = false;
		window.__razorpay_payment_completed = false;

		var options = {
			"key": "{{ api_key }}",
			"amount": cint({{ amount }} * 100), // 2000 paise = INR 20
		"currency": "{{ currency }}",
			"name": "{{ title }}",
				"description": "{{ description }}",
					"subscription_id": "{{ subscription_id }}",
						"order_id": "{{ order_id }}",
		"modal": {
			"ondismiss": function () {
				// User closed the Razorpay modal (treat as cancelled).
				// Note: Razorpay may close the modal after a successful payment too (race with handler).
				// So we delay redirect a bit and cancel it if handler runs.
				window.__razorpay_flow_cancelled = true;
				setTimeout(function () {
					if (window.__razorpay_payment_completed) return;
					window.location.href = "/payment-cancel?token={{ token }}";
				}, 1200);
			}
		},
							"handler": function (response) {
								window.__razorpay_payment_completed = true;
								window.__razorpay_flow_cancelled = false;
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
rzp.on("payment.failed", function (response) {
	// Record the error against the Integration Request, then redirect.
	frappe.call({
		method: "payments.payment_gateways.doctype.razorpay_settings.razorpay_settings.order_payment_failure",
		freeze: false,
		headers: { "X-Requested-With": "XMLHttpRequest" },
		args: {
			"integration_request": "{{ token }}",
			"params": JSON.stringify(response && response.error ? response.error : response)
		},
		always: function () {
			window.location.href = "/payment-failed?token={{ token }}";
		}
	});
});
rzp.open();
		//	e.preventDefault();
	}) ();
})

frappe.provide('razorpay');

razorpay.make_payment_log = function (response, options, doctype, docname, token) {
	if (window.__razorpay_flow_cancelled) return;
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
				// If Frappe nested our custom URL as a query parameter, unwrap it
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
