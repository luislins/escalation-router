# Past escalations

Bugs that were escalated before, grouped by the team that fixed them. The people listed
under "resolved by" are the only names you may give as "fixed similar bugs".

## Payments (`payments`)

- **ESC-101**: Donor card declined with 'authentication required' on every attempt from EU cards — resolved by Bruno Lima. Root cause: 3DS challenge was skipped for EU cards after gateway upgrade; restored SCA flow.
- **ESC-105**: Organization payout delayed 5 days, balance shows pending — resolved by Carla Mendes. Root cause: Bank account verification expired; prompted org to re-verify.
- **ESC-115**: Refund issued in dashboard but donor never got the money back — resolved by Ana Souza. Root cause: Refund stuck in gateway pending state; retried via gateway API.

## Donor Experience (`donor-experience`)

- **ESC-102**: Embedded donation widget shows blank iframe on WordPress site — resolved by Diego Rocha. Root cause: CSP frame-ancestors header was too strict for custom domains.
- **ESC-110**: Donor cannot cancel monthly donation from donor portal — resolved by Elisa Martins. Root cause: Cancel button hidden on mobile due to CSS regression.
- **ESC-116**: Donation form currency shows USD symbol for GBP campaign — resolved by Diego Rocha. Root cause: Locale fallback ignored campaign currency.

## Integrations (`integrations`)

- **ESC-103**: Salesforce sync creating duplicate contacts for returning donors — resolved by Gabriela Costa. Root cause: Email matching was case sensitive; normalized before upsert.
- **ESC-108**: Webhook for donation.created not firing for recurring payments — resolved by Felipe Araujo. Root cause: Recurring charges emitted a different event type; added mapping.
- **ESC-113**: Mailchimp audience not receiving new donors tags — resolved by Henrique Alves. Root cause: Mailchimp API rate limit hit; added backoff.

## Reporting & Receipts (`reporting`)

- **ESC-104**: Year-end tax receipt PDF shows wrong total for donors with refunds — resolved by Isabela Nunes. Root cause: Refunded amounts were not subtracted in receipt aggregation.
- **ESC-109**: Thank you email not received by donors using Outlook — resolved by Joao Pereira. Root cause: SPF record missing for new sending domain.
- **ESC-114**: CSV export of donations times out for large organizations — resolved by Isabela Nunes. Root cause: Moved export to background job with emailed link.

## Campaigns & Events (`campaigns`)

- **ESC-106**: Peer-to-peer fundraiser page goal meter not updating after donation — resolved by Karina Dias. Root cause: Cache on campaign totals was not invalidated by new donations.
- **ESC-111**: Event tickets QR code not scanning at check-in — resolved by Leonardo Freitas. Root cause: QR payload exceeded scanner size limit; shortened token.

## Platform & Identity (`platform`)

- **ESC-107**: Admin cannot invite new team member, gets access denied — resolved by Mariana Gomes. Root cause: Seat limit check used the wrong plan tier.
- **ESC-112**: Users locked out after enabling 2FA, codes always invalid — resolved by Nicolas Barros. Root cause: Server clock drift on one auth node.
