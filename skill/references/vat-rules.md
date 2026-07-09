# Reverse charge & VAT rules (read the invoice — never guess)

Assumes a **UK VAT-registered business on the standard scheme**. These rules decide how a purchase
is recorded. **You must open the invoice PDF and read it — the bank description and the vendor's
web domain are not enough.** (If the business is on the Flat Rate Scheme or not VAT-registered,
these rules differ — confirm the scheme first via `GET /v2/company`.)

## The one rule that matters

Look at the invoice for **(a) the supplier's country/entity** and **(b) whether UK VAT was
actually charged**:

| What the invoice shows | Treatment | API |
|---|---|---|
| Non-UK supplier, **0% / no VAT**, often says "reverse charge" | **Reverse charge** | `ec_status="Reverse Charge"`, `sales_tax_rate="AUTO"` |
| Any supplier that **charged UK VAT** (a GB VAT line, 20%/5%) | Standard UK purchase — reclaim the input VAT | `ec_status="UK/Non-EC"`, `sales_tax_rate="20.0"` (or 5.0) |
| UK supplier, no VAT (exempt/zero-rated) | Domestic, no reclaim | `ec_status="UK/Non-EC"`, `sales_tax_rate="0.0"` |

## Why you cannot trust the `.com`

Illustrative real-world cases (public-company facts) where a name-heuristic gets it **wrong** —
US/EU-looking vendors that are actually UK-VAT-registered and charge 20%:
- A popular developer tool on a `.com` domain → operates a **UK Ltd** and charges 20% UK VAT.
- A big US AI provider → **GB VAT-registered**, charges 20% UK VAT on some plans.
- A US software giant billed via an obscure descriptor → its **UK Ltd** entity, charges 20% UK VAT.

And genuinely reverse-charge: most US/EU/rest-of-world SaaS that bill at **0% / no UK VAT** (an EU
supplier's invoice often literally says "reverse charge"; a US supplier simply shows no VAT line).

The point: **a foreign-looking vendor may still register for UK VAT and charge it — and a
UK-looking one may not.** Only the invoice reveals which.

## About "AUTO" (important, non-obvious)

For a reverse charge, FreeAgent only accepts `sales_tax_rate` of `"AUTO"` or `"0.0"` — a positive
rate is rejected (422). **"AUTO" is not a stored value — it's an instruction** telling FreeAgent to
resolve the rate; it resolves reverse charges to **0%** and that is correct. The reverse charge
itself (the notional 20% into VAT Boxes 1 & 4, net-zero) is driven by the `ec_status` flag, not the
rate. So a reverse-charge line correctly shows rate 0% with `ec_status="Reverse Charge"`. Setting
AUTO on every reverse-charge write is harmless and confirms the pipeline is doing what you expect.

## Travel — UK rail (e.g. Trainline) is zero-rated, not reverse charge

UK **rail passenger transport is zero-rated (0% VAT)** — there is no VAT to reclaim on a train
fare. So a Trainline booking is a **domestic UK** transaction: category **Travel**,
`ec_status = "UK/Non-EC"`, `sales_tax_rate = "0.0"`. **Not reverse charge** — even though a
Trainline receipt footer also lists a French entity, UK rail is billed by the UK company and is
zero-rated. The small booking fee doesn't change this in practice. Same logic for most UK travel
(bus, most taxis). Contactless transit journeys have no receipt at all — leave them without an
attachment.

## Filed VAT periods — flag, don't fix

VAT returns already filed cannot be corrected by editing the old transaction. If you find a VAT
error (wrong ec_status) in a **filed** period, do **not** change it — surface it for the accountant
with supplier, date, amount, the error, and which VAT quarter. Check filed periods via
`GET /v2/vat_returns` (`filing_status`). Attaching an invoice is always safe even in a filed period
(documentation only, doesn't move VAT figures).
