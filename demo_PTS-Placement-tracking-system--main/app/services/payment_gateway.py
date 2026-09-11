"""
Payment gateway integration - SRS FR-09.

This module is intentionally a thin, provider-agnostic shell. It cannot be
fully wired up without a real Razorpay/Cashfree/Stripe account and API keys
(entered on the Integrations page once app/models/platform_settings.py has
the payment_gateway_* columns from platform_settings_gateway_patch.py.diff)
- there is nothing to test end-to-end without those.

What IS real here: the Invoice bookkeeping. `mark_invoice_paid` is what a
real webhook handler (or a manual "Mark as Paid" button) should call - it's
the one place that updates both the Invoice and the Organization consistently.

To finish wiring a provider:
  1. pip install razorpay (or cashfree-pg, or stripe)
  2. Fill in `create_payment_link` for that provider using the credentials
     from get_payment_gateway_config()
  3. Add a webhook route (e.g. POST /webhooks/payment/<provider>) that
     verifies the signature using payment_gateway_webhook_secret, then
     calls mark_invoice_paid() or mark_invoice_failed() based on the event.
"""

import logging

from app.extensions import db
from app.models import Invoice
from app.utils.platform_settings import get_platform_settings

logger = logging.getLogger(__name__)


def get_payment_gateway_config():
    """Returns (provider, key_id, key_secret, webhook_secret). All may be
    None/blank if the super admin hasn't configured a gateway yet - callers
    must check before attempting to create a payment link."""
    settings = get_platform_settings()
    return (
        settings.payment_gateway_provider,
        settings.payment_gateway_key_id,
        settings.payment_gateway_key_secret,
        settings.payment_gateway_webhook_secret,
    )


def is_gateway_configured():
    settings = get_platform_settings()
    return bool(
        settings.payment_gateway_enabled
        and settings.payment_gateway_provider
        and settings.payment_gateway_key_id
        and settings.payment_gateway_key_secret
    )


def create_payment_link(invoice: Invoice):
    """Returns a checkout URL the organization can be sent to pay this
    invoice. Raises RuntimeError if no gateway is configured, or
    NotImplementedError for a configured provider whose SDK call hasn't
    been filled in yet (see module docstring).

    Each branch below is scaffolding, not a working call - it shows the
    shape (invoice.amount in the provider's expected unit, a reference id
    to correlate the webhook back to this Invoice, etc.) so wiring in the
    real SDK is a small, obvious diff rather than a redesign.
    """
    provider, key_id, key_secret, _ = get_payment_gateway_config()

    if not is_gateway_configured():
        raise RuntimeError(
            "No payment gateway is configured. Set one up on the Integrations page first."
        )

    if provider == "razorpay":
        raise NotImplementedError(
            "Fill in with: razorpay.Client(auth=(key_id, key_secret)).payment_link.create({...}), "
            "using invoice.amount * 100 (paise) and invoice.invoice_number as reference_id."
        )
    elif provider == "cashfree":
        raise NotImplementedError(
            "Fill in with Cashfree PG's create-order API using key_id/key_secret, "
            "invoice.amount, and invoice.invoice_number as order_id."
        )
    elif provider == "stripe":
        raise NotImplementedError(
            "Fill in with stripe.checkout.Session.create(...) using key_secret as the API key, "
            "invoice.amount * 100 (cents), and invoice.invoice_number in metadata."
        )
    else:
        raise RuntimeError(f"Unknown payment gateway provider: {provider!r}")


def mark_invoice_paid(invoice: Invoice, gateway=None, gateway_reference=None, raw_response=None, actor_id=None):
    """The single place that should ever flip an invoice + its organization
    to paid - called either by a webhook handler or a manual 'Mark as Paid'
    action in the UI (pass gateway='manual' for the latter)."""
    from datetime import datetime

    from app.models import Organization

    invoice.status = "PAID"
    invoice.paid_at = datetime.utcnow()
    invoice.payment_gateway = gateway
    invoice.gateway_reference = gateway_reference
    invoice.gateway_raw_response = raw_response
    invoice.modified_by = actor_id

    org = Organization.query.get(invoice.organization_id)
    if org:
        org.payment_status = "PAID"
        # Note: Organization.modified_by is an integer column (unlike the
        # UUID-string modified_by used on Plan/Role/Module elsewhere in this
        # codebase) and isn't set anywhere else in the app either, so it's
        # left untouched here rather than passing an incompatible UUID
        # actor_id into it.
        org.modified_at = datetime.utcnow()

    db.session.commit()
    return invoice