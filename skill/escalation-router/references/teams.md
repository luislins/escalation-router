# Teams and what they own

Triage team when nothing fits or confidence is low: `support-escalations`.

## Payments (`payments`)

Slack channel: #team-payments

Card and bank processing, payment gateways, refunds, disputes, payouts to organizations.

- **Card processing**: stripe, card, declined, charge, 3ds, authentication, apple pay, google pay, wallet
  - services: payments-api, gateway-adapter
- **Refunds and disputes**: refund, chargeback, dispute, reversal
  - services: payments-api
- **Payouts**: payout, transfer, bank account, settlement, balance, stripe connect
  - services: payouts-worker
- **Bank payments**: ach, sepa, bacs, direct debit, pix, bank transfer
  - services: gateway-adapter

## Donor Experience (`donor-experience`)

Slack channel: #team-donor-experience

Donation forms, embedded widgets, checkout flow, donor portal.

- **Donation forms**: form, widget, embed, iframe, checkout, button, amount, custom field, popup
  - services: forms-frontend, forms-api
- **Recurring donations (donor side)**: recurring, monthly, subscription, cancel donation, update card, donor portal
  - services: donor-portal
- **Localization**: translation, language, currency display, locale, rtl
  - services: forms-frontend

## Integrations (`integrations`)

Slack channel: #team-integrations

Third-party CRM and marketing syncs, webhooks, public API, Zapier.

- **CRM sync**: salesforce, hubspot, bloomerang, crm, sync, mapping, duplicate contact
  - services: sync-worker
- **Marketing tools**: mailchimp, constant contact, audience, list, tag
  - services: sync-worker
- **Webhooks and public API**: webhook, api key, zapier, endpoint, rate limit, 401, callback
  - services: public-api, webhook-dispatcher

## Reporting & Receipts (`reporting`)

Slack channel: #team-reporting

Dashboards, exports, tax receipts, year-end statements, emails sent to donors.

- **Tax receipts**: receipt, tax, year-end, statement, pdf, 501c3, gift aid
  - services: receipts-worker
- **Exports and dashboards**: export, csv, report, dashboard, chart, totals, analytics
  - services: reports-api
- **Transactional email**: email, thank you email, not received, bounce, template
  - services: mailer

## Campaigns & Events (`campaigns`)

Slack channel: #team-campaigns

Campaign pages, peer-to-peer fundraising, events and ticketing, memberships.

- **Peer-to-peer**: peer-to-peer, p2p, fundraiser page, team page, goal meter, leaderboard
  - services: campaigns-api
- **Events and ticketing**: event, ticket, qr code, check-in, attendee, registration
  - services: events-api
- **Memberships**: membership, member, tier, renewal
  - services: campaigns-api

## Platform & Identity (`platform`)

Slack channel: #team-platform

Login, 2FA, user roles and permissions, org accounts, performance and outages.

- **Authentication**: login, password, 2fa, sso, saml, session, locked out, magic link
  - services: auth-service
- **Permissions and org accounts**: role, permission, invite, team member, admin, access denied, 403
  - services: accounts-api
- **Reliability**: outage, 500, timeout, slow, down, latency, error page, deploy
  - services: edge, core-web

## Support Escalations (triage rotation) (`support-escalations`)

Slack channel: #support-escalations

Human triage rotation. Receives anything the router cannot place with confidence.

