---
title: Legal, Compliance & Risk Management Blueprint
status: Draft
last-verified: 2026-11-07
---

# BlackEclipse Legal & Compliance Blueprint

**Who this is for:** founders, maintainers, contributors, and anyone who will
operate a hosted BlackEclipse service.

**What this is:** a practical risk-management blueprint for an open-source,
self-directed financial research and order-entry platform. It explains what can
actually go wrong, which legal regimes may apply, which controls reduce exposure,
which documents to ship, and what to do when someone claims a loss.

**What this is not:** legal advice, a substitute for a licensed lawyer in your
jurisdiction, or a guarantee that any wording will prevent a lawsuit. No
disclaimer, waiver, licence, or corporate structure is immunity. This document
describes the defensible position and the evidence needed to support it.

**Date-sensitive:** written 2026-11-07. Financial regulation, AI regulation, and
data-protection law change frequently. Re-check before launch and before entering
a new country.

---

## 0. The short answer

Your instinct is correct:

> **Eclipse is a tool. You make the decisions. You own the outcome. Eclipse does
> not manage your money, does not guarantee results, and does not share your
> profits or losses.**

That sentence is necessary. It is not sufficient. A disclaimer is evidence of
what the user agreed to; it is not a force field. It can be overridden by consumer
law, ignored where the product's behaviour contradicts it, and it never protects
against fraud, deliberate misconduct, or a regulator deciding that what you call
"software" is actually a regulated service.

The defensible version is a package of five things, in this order:

1. **Entity separation** - a real company, with IP assigned to it, accounts and
   contracts in its name.
2. **A contract the user actually accepts** - clickwrap Terms, Privacy, Risk
   Disclosure, and an Acceptable Use Policy, versioned and logged.
3. **Product behaviour consistent with the contract** - no discretion, no
   custody, no pooled money, no guaranteed returns, no hidden advice, and
   explicit user authorisation for every order.
4. **Evidence** - audit trails that let you reconstruct who authorised what, with
   which model, data, code version, and order digest.
5. **Insurance and a response plan** - because even a defensible position costs
   money to defend.

Remove any one of those and the sentence becomes marketing.

### The seven highest-value actions

| Rank | Action | Why it matters | Effort |
|---|---|---|---|
| 1 | Incorporate and assign all IP to the company | Separates personal assets; makes contracts and insurance possible | 1-3 weeks |
| 2 | Ship clickwrap Terms + Privacy + Risk Disclosure + AUP | Creates the contractual relationship your disclaimers depend on | 1-2 weeks |
| 3 | Gate live trading behind a recorded, specific risk acknowledgment | The single highest-risk feature needs the clearest consent | 2-5 days |
| 4 | Keep the no-discretion / no-custody / no-pooling invariant | This is what keeps you a software tool rather than a regulated manager | Product discipline |
| 5 | Preserve audit evidence for every order and every AI recommendation | Your best defence is a reconstructable record | Already mostly built |
| 6 | Never store broker passwords; prefer local attach / OAuth | Credential compromise is the most damaging realistic incident | Already designed |
| 7 | Add a trademark policy and a DCO | Protects the name and keeps contribution clean without a CLA | 1 day |

### What not to do

- Do not say "we are not responsible for anything" in a way that contradicts the
  product. Broad waivers that a court finds unfair can damage credibility and may
  be void.
- Do not describe the platform as "guaranteed", "risk-free", "profitable",
  "accurate", or "a replacement for a financial adviser".
- Do not add discretionary managed accounts, copy-trading, pooled funds,
  performance fees, or custody without licensed advice. Those are different
  businesses.
- Do not treat the MIT licence as a user contract or as protection for a hosted
  service.
- Do not launch live trading in a new country because "the website is in
  English". Targeting is a legal question, not a language question.

---

## 1. Legal structure and liability

### 1.1 What structure to use

**Recommendation, in order of preference:**

| Situation | Structure | Why |
|---|---|---|
| Founder/operator resident in Pakistan; self-hosted + early hosted service | **Pakistan private limited company (SECP)** | Real legal person, limited liability, local bank account, enforceable contracts, lower cost than offshore |
| Majority of paying users in the UK/EU and a UK founder | **UK private limited company** | Familiar contract law, FCA-facing credibility, inexpensive formation |
| Venture funding, US investors, or a US-facing hosted product | **Delaware C-Corp** (possibly with a Pakistani/UK operating subsidiary) | Standard for investment; not automatically better for a bootstrapped project |
| Pure open-source project with no revenue and no hosted service | Company still recommended once there is any live trading or user data | A sole proprietor has unlimited personal liability |

Do **not** operate as a sole proprietorship once the platform can place orders or
hold user data. Do not run the hosted service through a personal bank account.
Do not let the company exist only on paper.

**Practical formation checklist:**

- [ ] Reserve the company name and register with SECP (or the equivalent).
- [ ] Obtain a tax registration/NTN and a business bank account.
- [ ] Adopt written constitution/articles that permit software licensing and
      financial-technology services.
- [ ] Issue founder shares and sign a **founder IP assignment** (all code,
      designs, domain names, trademarks, content, and prior work used by the
      project).
- [ ] Sign **contractor IP assignments** for anyone paid to build.
- [ ] Put the domain, GitHub organisation, trademarks, and payment accounts in
      the company's name (or assign them).
- [ ] Keep personal and company money separate; document any loan from a founder.
- [ ] Maintain minutes for major decisions (licence change, live trading launch,
      terms changes).
- [ ] File annual returns and tax; a struck-off company offers no protection.

**Cost reality (2026, indicative):**

| Item | Pakistan | UK | US (Delaware) |
|---|---|---|---|
| Formation + registered agent | USD 100-500 | USD 100-500 | USD 500-2,000 |
| Annual compliance | USD 100-400 | USD 100-500 | USD 500-2,500 |
| Local lawyer review | USD 300-1,500 | USD 500-2,000 | USD 1,500-5,000 |

These are planning ranges, not quotes.

### 1.2 Separation is not absolute

A company separates liability only if it is respected. Courts and regulators can
reach founders or maintainers where there is:

- fraud, deliberate concealment, or personal misrepresentation;
- personal guarantees (common for office leases, banking, or payment processing);
- commingling of funds or treating the company as an alter ego;
- unpaid taxes or statutory liabilities;
- personal torts (for example, defamation or knowingly shipping malicious code);
- a director's statutory duties (insolvent trading, filings, safety).

Maintainers and contributors are usually not personally liable for ordinary bugs
in open-source code, but they can be liable for **knowingly** shipping malware, a
backdoor, infringing code, or a false warranty they personally gave. The MIT
licence's warranty disclaimer helps, but it does not bind users of a hosted
service and does not cover fraud or personal misconduct.

### 1.3 Who bears what

| Role | Main exposure | Main protection |
|---|---|---|
| Founder/director | Company obligations, payroll/tax, regulatory breach, personal guarantees | Entity, D&O insurance, written role limits, advice at triggers |
| Maintainer | Security incidents, IP claims, support expectations, burnout-driven mistakes | Clear maintainer policy, security process, DCO, no personal warranties |
| Contributor | Infringing contribution, malicious code, personal warranty | DCO, contribution terms, review, licence disclaimer |
| Hosted operator | Contract, privacy, security, regulatory characterisation, outages | ToS, DPA, security programme, insurance, jurisdiction limits |
| Self-hosted user | Their own data, broker account, trading losses, local law | In-app notices, docs, no support promise |
| Broker | Execution, account suitability, its own terms | User contracts directly with broker; Eclipse is not a party |

### 1.4 Contributor agreements

**Use a DCO, not a CLA, unless you need to relicense.**

- **DCO (Developer Certificate of Origin):** the contributor signs off that they
  have the right to submit the code under the project licence. Cheap, familiar,
  low-friction, and sufficient for MIT/Apache projects. Add a `DCO` file and a
  `Signed-off-by:` requirement.
- **CLA (Contributor Licence Agreement):** gives the company broader rights
  (relicensing, dual licensing, patent grants). Useful if you may sell a
  proprietary edition or change licence later. It deters some contributors and
  adds administrative work.

**Recommendation:** adopt a DCO now; add a CLA only if a dual-licence or
relicensing plan becomes real. If you accept a CLA, make it public, plain-English,
and record signatures.

**Contributor policy should state:**

- contributions are licensed inbound under the project licence (inbound =
  outbound);
- no warranty is given by the contributor;
- maintainers may reject, edit, or remove contributions;
- no entitlement to support, roadmap influence, or revenue;
- security reports follow `SECURITY.md`;
- the code of conduct applies.

### 1.5 Terms of use: the clauses that matter

Do not copy a generic SaaS template. These clauses are the ones that actually map
to this product:

1. **Acceptance and versioning** - clickwrap, not browsewrap; record user, time,
   version, IP, and user agent.
2. **Eligibility and jurisdiction** - age, legal capacity, sanctions, restricted
   territories, and a representation that the user may lawfully use the service.
3. **Nature of the service** - self-directed research and order-entry software;
   not a broker, adviser, fiduciary, fund manager, or custodian.
4. **No advice / no recommendation** - outputs are informational, may be wrong,
   and are not tailored to the user's circumstances.
5. **Risk acknowledgment** - leveraged products can lose more than deposited;
   past performance and backtests do not predict results.
6. **User authority** - the user owns the broker account, is authorised to trade
   it, and authorises each order.
7. **Execution** - Eclipse transmits the user's instruction; the broker is the
   source of truth; fills, slippage, rejection, and outages are outside Eclipse's
   control.
8. **AI disclosure** - probabilistic output, hallucinations, data gaps, model
   changes, and no guarantee of accuracy.
9. **Data and privacy** - reference to the Privacy Notice and DPA if hosted.
10. **Acceptable use** - no unlawful trading, market abuse, third-party accounts,
    credential sharing, scraping, or resale of signals.
11. **IP and licence** - the software licence; the user's data remains theirs;
    feedback licence.
12. **Third-party services** - brokers, data providers, model providers, MCP
    servers; their terms govern.
13. **Disclaimers** - specific, conspicuous, and consistent with the product.
14. **Limitation of liability** - cap, exclusion of indirect loss; **do not**
    purport to exclude fraud, wilful misconduct, death/personal injury, or
    non-excludable consumer rights.
15. **Indemnity** - user indemnifies Eclipse for misuse, third-party account
    access, or breach; carve out where unenforceable.
16. **Termination and suspension** - including for regulatory or security risk.
17. **Changes** - notice and re-acceptance for material changes.
18. **Governing law and disputes** - chosen law, courts/arbitration, consumer
    carve-outs.
19. **Contact and complaints** - a real channel and response target.

**Consumer warning:** in the EU, UK, Pakistan, and many other jurisdictions,
unfair terms in consumer contracts can be struck out. A clause that says "we are
liable for nothing" is likely to fail. Aim for a **clear allocation of risk**,
not a fantasy of zero liability.

---

## 2. Financial regulatory compliance

### 2.1 The spectrum that decides everything

Regulation follows **substance and activity**, not the label on the website. The
further right you move, the more likely a licence is required.

| Position | What it looks like | Regulatory characterisation (indicative) |
|---|---|---|
| 1. Data and calculators | Quotes, charts, indicators, backtests, portfolio accounting | Usually software/data; lowest risk |
| 2. General research | Market commentary, education, impersonal analysis | Often publishing/editorial; publisher exclusions may help in the US, but not universally |
| 3. AI-generated analysis | "Here is an analysis of AAPL" | Still potentially general information, but personalisation and actionable language increase risk |
| 4. Personalised recommendation | "You should sell 30% of your NVDA because of your risk profile" | Likely **investment advice** in the UK/EU; possibly adviser activity in the US |
| 5. Signals / auto-strategies | "Follow this strategy; it will trade your account" | May be **advice**, **portfolio management**, or a **commodity trading advisor** depending on structure |
| 6. Order entry on user instruction | User clicks "buy"; Eclipse sends to the user's broker | May be **arranging/transmitting orders** or broker activity; structure matters |
| 7. Discretionary management | Eclipse decides without a per-order instruction | Almost certainly **regulated portfolio management** |
| 8. Custody / pooling | Eclipse holds client money or trades a pooled fund | **Broker/dealer, custodian, fund manager** territory; highest risk |
| 9. Performance fees / profit share | Eclipse takes a share of gains | Strong evidence of an advisory/management relationship |

**Your defensible design target is position 3 plus position 6, with position 7-9
off the table.** You can provide research and let a user authorise an order. You
should not decide the order, size it without the user's parameters, hold the
money, pool users, or take a cut of profits.

### 2.2 What changes when you move along the spectrum

**Research tools -> investment advice** when the output is:

- personalised to a specific user's portfolio, risk tolerance, tax position, or
  goals;
- presented as a recommendation to buy/sell/hold;
- not accompanied by sufficient information for the user to make their own
  decision;
- delivered with an expectation of reliance (especially if paid for).

**Advice -> portfolio management** when you have discretion or a mandate to
manage, even if a human clicks "approve" after the system decides everything.

**Order entry -> brokerage** when you transmit orders for another person as a
business, hold themselves out as executing, handle client money, or receive
transaction-based compensation in a way regulators treat as brokerage.

**Software -> financial promotion** when marketing communicates an invitation or
inducement to engage in investment activity. This is separate from advice and is
strictly regulated in the UK and EU.

### 2.3 Jurisdiction snapshot

This is a map, not a legal opinion. Confirm each item with local counsel before
targeting that market.

#### United States

| Regime | Trigger | Why it matters |
|---|---|---|
| Investment Advisers Act 1940 | Providing advice about securities for compensation as a business | Registration/notice filing; fiduciary duties; the "publisher's exclusion" is narrow and does not cover personalised advice |
| Securities Exchange Act 1934, Section 15 | Acting as a broker or dealer | Order transmission, solicitation, and transaction-based compensation can trigger broker-dealer registration |
| Investment Company Act 1940 | Pooling money into a fund | Avoid pooling entirely |
| Commodity Exchange Act / CFTC | Futures, options, retail forex/CFDs, advising on them | CTA/CPO registration; NFA membership; retail forex rules; hypothetical-performance rules |
| FinCEN / state money transmission | Holding or moving user funds | Avoid custody; use the user's own broker |
| State securities laws | Intrastate advice or broker activity | Separate state registration/notice requirements |
| FTC Act / state consumer protection | Deceptive marketing, unfair practices | "Guaranteed returns" and undisclosed risks are the danger |

The **publisher's exclusion** (often associated with *Lowe v. SEC*) protects
genuine, impersonal, general-circulation publishing. It is not a safe harbour for
an interactive AI that says "you should buy 100 shares". If the system asks for a
user's portfolio and tailors the answer, assume the exclusion is weak or
unavailable.

#### United Kingdom

| Regime | Trigger | Why it matters |
|---|---|---|
| FSMA 2000 + Regulated Activities Order | Advising on investments, arranging deals, managing investments, safeguarding | FCA authorisation or an applicable exclusion |
| Financial promotion regime | Marketing that invites or induces investment activity | Criminal offence for unauthorised firms, with limited exemptions |
| Consumer Duty | Retail customers | Fair value, consumer understanding, good outcomes |
| FCA crypto regime | Cryptoasset activities | Separate authorisation path |
| UK GDPR / DPA 2018 | Personal data | See section 5 |

The **overseas persons exclusion** and **reverse solicitation** are narrow and
fact-specific. A website accessible in the UK, with UK-facing marketing, is not
automatically outside the regime.

#### European Union

| Regime | Trigger | Why it matters |
|---|---|---|
| MiFID II | Investment advice, portfolio management, execution of orders, operating an MTF/OTF | Authorisation, conduct rules, suitability, best execution, reporting |
| AIFMD / UCITS | Pooled funds | Avoid pooling |
| PRIIPs / KID | Packaged retail products | If you distribute or advise on them |
| DORA | Digital operational resilience for financial entities and critical ICT providers | Hosted financial services and vendor contracts |
| AI Act | AI systems, especially transparency and high-risk uses | Chatbot disclosure; some finance uses may be high-risk |
| MAR | Market abuse, insider dealing, manipulation | User behaviour and platform features must not facilitate abuse |
| GDPR | Personal data | Extraterritorial reach |

MiFID II is the key one: **personal recommendations** and **discretionary
management** are licensed activities. "Execution-only" is a narrower regime, but
it still carries obligations and is not a magic exemption.

#### Pakistan

| Regime | Trigger | Why it matters |
|---|---|---|
| Securities Act 2015 / SECP | Securities market intermediaries, brokers, advisers | Licensing and conduct rules |
| NBFC Rules / SECP | Non-bank financial companies, investment advisory, asset management | A licensed activity if you hold out as an adviser/manager |
| SBP | Banking, foreign exchange, remittances, payment services | Custody or money movement |
| PECA 2016 | Cybercrime, unauthorised access, data misuse | Security and incident exposure |
| Data protection | Pakistan's data-protection framework is still developing | Track the current bill/regulations; do not assume GDPR-equivalent rules do not apply |
| Consumer protection | Federal/provincial consumer laws | Unfair terms and misleading claims |

**Practical Pakistan position:** a self-hosted software tool with no custody, no
discretion, and no Pakistan-facing solicitation is unlikely to be a licensed
securities activity. A hosted service that markets investment advice, manages
portfolios, or executes for clients in Pakistan is a different question and needs
SECP/SBP advice. This is one of the highest-uncertainty areas in this document.

### 2.4 Cross-border reality

- **Targeting matters.** Language, currency, local payment methods, local events,
  local influencers, and country-specific landing pages all point toward
  targeting.
- **Geo-blocking helps but is not absolute.** Determined users use VPNs. Keep the
  block, the attestation, and the logs; they show intent.
- **Reverse solicitation is narrow.** "The user found us" does not automatically
  exempt you if you then solicit or advise.
- **One country at a time.** Do not add a jurisdiction because a user asked. Add
  it after a local review.
- **Separate the OSS project from the hosted service.** The licence can be
  worldwide; the hosted service's availability need not be.

### 2.5 The twelve red-flag test

If you answer "yes" to any of these, get licensed advice before shipping:

1. Do you tell a specific user what to buy, sell, hold, or size?
2. Do you ask for their income, net worth, goals, or risk tolerance and tailor the
   output?
3. Do you manage money without a per-order instruction?
4. Do you hold, receive, or transmit client money?
5. Do you pool users into one account or strategy?
6. Do you charge a performance fee or share profits?
7. Do you let users copy another user's trades automatically?
8. Do you market expected returns, win rates, or "passive income"?
9. Do you execute orders for users who are not the account owner?
10. Do you operate in a country where you have no legal advice and no local
    entity?
11. Do you earn transaction-based compensation from a broker?
12. Do you tell users the AI is accurate, safe, or a substitute for an adviser?

### 2.6 The posture to document

Write this down and make the product match it:

> BlackEclipse is self-directed software. It provides data, research,
> computation, and order-entry tools. It does not manage accounts, exercise
> discretion, hold client assets, pool funds, recommend specific trades as a
> fiduciary, or guarantee outcomes. The user is the decision-maker and the
> account owner. Any order is initiated and authorised by the user. The broker is
> the source of truth for execution.

Then check every feature and every marketing sentence against it.

---

## 3. AI and financial risk disclosures

### 3.1 What a disclaimer can and cannot do

| Works (as evidence and risk allocation) | Does not work (or is weak) |
|---|---|
| A specific, conspicuous notice at the point of use | A vague "use at your own risk" buried in a footer |
| A recorded acceptance of a named risk | A blanket waiver of all liability, including fraud or negligence |
| A statement that is true of the product's behaviour | A statement contradicted by the UI or marketing |
| A clear explanation of uncertainty and data limits | "AI can be wrong" with no explanation of what that means |
| A limitation of liability that is reasonable and negotiated | A clause that purports to override consumer rights |
| A warning that a forecast is hypothetical | Presenting a backtest as a track record |
| A statement that the user must verify at the broker | Claiming an order is filled when it is only submitted |

The legal test is usually **conspicuousness, specificity, timing, consistency, and
reliance**. A disclaimer shown once at signup, contradicted by a "95% win rate"
banner, is not credible.

### 3.2 The layered disclosure model

Use all five layers, not one:

1. **Global documents** - Terms, Risk Disclosure, AI Disclosure, AUP.
2. **First-run acknowledgment** - a modal the user must accept, with a recorded
   version and timestamp.
3. **Point-of-use labels** - every analysis surface says what it is and is not.
4. **Output-level provenance** - source, timestamp, freshness, computed vs
   sourced vs unverified, model/provider identity where relevant.
5. **Action-level confirmation** - before a live order, show the exact order,
   worst-case risk, and require the user's authorisation.

### 3.3 What the AI disclosure should say

Keep it short enough to be read, specific enough to be useful:

> Eclipse uses probabilistic AI models. Outputs can be incomplete, outdated,
> wrong, or fabricated, even when they look confident. They are not a
> recommendation, not a substitute for your own research or a licensed adviser,
> and not a promise of future results. Market data may be delayed, missing, or
> incorrect. You must verify prices, orders, and positions with your broker before
> acting. You are responsible for your decisions.

Then add the product-specific facts:

- which model/provider is in use, if the user can choose;
- whether data leaves the machine (privacy mode);
- that backtests are hypothetical and subject to survivorship, look-ahead,
  overfitting, and cost assumptions;
- that the AI may use tools, browse the web, or call MCP servers, and those
  results are not verified by Eclipse;
- that the user should not rely on the output for tax, legal, or accounting
  decisions.

### 3.4 Hallucinations, bad data, and model failure

You already have unusually strong controls for this class of product:

- the **Fiduciary Gate** (`docs/fiduciary-advice.md`) extracts actionable claims
  and labels them `COMPUTED`, `SOURCED`, or `UNVERIFIED`;
- the finance-fact and citation release gates verify figures and sources;
- observation freshness (`live`/`delayed`/`stale`/`historical`/`unavailable`) is
  exposed rather than smoothed over;
- the quant/portfolio engines return `UNAVAILABLE` rather than inventing data;
- the Advisory Ledger records what was recommended, on what basis, and how it
  turned out.

**Keep these as product invariants.** Do not let a marketing page or a new surface
bypass them. If a feature cannot show provenance, it should show `UNAVAILABLE`,
not a plausible number.

**Do not auto-execute from an `UNVERIFIED` recommendation.** The existing design
keeps recommendations proposal-only; preserve that. If you ever allow an agent to
trade from its own analysis, that is a different risk category and needs explicit
counsel and a much stronger mandate.

### 3.5 Marketing rules

The most common way a fintech disclaimer is defeated is marketing that promises
what the disclaimer denies. Prohibited or high-risk language:

- "guaranteed", "risk-free", "safe", "can't lose";
- "beat the market", "consistent returns", "passive income";
- "our AI is accurate" or "the AI never makes mistakes";
- cherry-picked backtests without the full period, costs, and survivorship
  assumptions;
- hypothetical performance presented as actual performance;
- testimonials that imply typical results without disclosure;
- "regulated" or "SEC/FCA-compliant" when you are not.

Use **"hypothetical", "simulated", "backtested", "not live"** labels wherever
applicable, and state the assumptions.

### 3.6 AI Act and chatbot transparency

If you serve EU users, the EU AI Act's transparency obligations are likely to
apply to a chatbot: users should know they are interacting with an AI. Do not
pretend the assistant is a human. If you generate synthetic content, label it.
Some finance uses can be high-risk; a generic research assistant is usually not,
but creditworthiness, insurance pricing, and similar uses are. Get advice before
expanding into those.

### 3.7 Model/provider terms

- Do not send user data to a model provider unless your privacy notice and the
  provider's terms permit it.
- Do not allow a provider to train on user data by default; prefer zero-retention
  or local models.
- Keep the provider list and data flows in the Privacy Notice.
- If the user supplies their own key, say so and explain that the provider's terms
  govern.
- Do not represent an MCP server's output as Eclipse-verified.

---

## 4. Automated trading and execution risk

### 4.1 The responsibility split

| Decision | Who should decide | Why |
|---|---|---|
| Whether to connect an account | User | The account is theirs; Eclipse is not a party to the broker contract |
| Whether to enable live trading | User, with a separate explicit acknowledgment | Highest-risk transition |
| Symbol, side, size, price, stop, target | User or user-configured strategy | This is the trading decision |
| Risk limits | User configures; Eclipse enforces | The user owns the risk budget |
| Order authorisation | User, per order (or a bounded, revocable mandate) | Keeps Eclipse an order-entry tool |
| Execution | Broker | Eclipse transmits; the broker fills |
| Reconciliation | Eclipse reads broker truth | Never invent a fill |
| Suitability | The user and their broker | Eclipse does not assess suitability |
| Compliance with local law | User; Eclipse provides attestation and geo-controls | Eclipse cannot verify every user's circumstances |

### 4.2 What you already have (and should advertise internally, not as a guarantee)

The broker layer is stronger than most retail trading tools:

- **Demo-first**: demo execution is the default path; live is a separate mode.
- **Arming**: live requires a typed `ARM LIVE <login>`, a real account, Algo
  Trading enabled, a non-zero magic, a positive `maxMargin`, and a time box.
- **Single-use approval**: an approval digest covers the exact order; a different
  order fails with `APPROVAL_ORDER_MISMATCH`.
- **Typed phrase**: every live order requires the exact `LIVE BUY 0.1 EURUSD`
  phrase; a missing phrase does not consume the approval.
- **Cooling-off** for high-value orders.
- **Risk limits**: per-trade risk, daily-loss brake, per-symbol notional,
  max open positions, max spread.
- **Kill switch**: cancels Eclipse-owned working orders (by magic) and disarms.
- **Risk-reducing exits are never blocked**: close/modify works even after the arm
  expires.
- **Mandates**: bounded by symbols, margin, order count, and expiry; live
  mandates are workflow-version-pinned and capped at 24 hours.
- **No blind retry**: an ambiguous `order_send` is marked `unknown`, not resent.
- **Reconciliation**: fills and positions are read back from the broker; a sync
  never fabricates a fill.
- **Audit**: broker ledger rows carry `runId`/`nodeId`, so a position can be traced
  back to the workflow run.
- **No credentials in the database**: MT5 uses local attach; password-shaped
  config is refused at write time.

This is exactly the kind of evidence that makes the "user is in control" story
credible. Keep it, test it, and document it.

### 4.3 Gaps to close before scaling live trading

| Gap | Recommendation | Priority |
|---|---|---|
| No recorded live-trading risk acknowledgment | A dedicated modal before the first live arm, versioned and logged | P0 |
| No jurisdiction gate | Country/region attestation + block restricted regions; log the decision | P0 |
| No account-ownership attestation | User confirms they own the broker account and may lawfully trade it | P0 |
| No "demo first" requirement | Require a demo connection or a completed paper session before live | P1 |
| No session-level loss cap | Add a per-session/day cap that disarms on breach (the daily-loss brake helps) | P1 |
| No anomaly detection | Alert on order velocity, size outliers, repeated rejects, and unusual symbols | P1 |
| No automatic disarm on suspicious activity | Disarm on repeated failures or a risk-limit breach; require re-arm | P1 |
| No clear "execution outage" runbook | Document what the user should do and what Eclipse will not do | P1 |
| No first-party trade-intent archive | Retain the intent, approval, arm, mandate, and outcome together | P1 |
| No copy-trading | Keep it out until counsel reviews it | Invariant |

### 4.4 Bugs, outages, and unexpected trades

You cannot promise that software will never fail. You can:

- **Fail closed** on authorisation, credential, and risk-limit errors.
- **Never retry an ambiguous send** (already implemented).
- **Show the broker's state**, not a guess.
- **Provide a kill switch** and risk-reducing exits.
- **Log the exact order intent and approval**, so the cause can be reconstructed.
- **Tell the user to verify at the broker** immediately after an ambiguous result.
- **Disclaim uptime and execution guarantees** in the Terms and Trading
  Disclaimer, without pretending that disclaims negligence.
- **Carry insurance** for the claims you can foresee.

The worst realistic scenario is not "the AI was wrong". It is "the software sent
an order the user did not intend, or failed to send an exit". Your controls should
target that scenario first.

### 4.5 Broker terms and credentials

- The user must comply with their broker's terms, including algo-trading and API
  permissions.
- Prefer **local attach** (MT5 terminal already logged in) over storing
  credentials.
- If you must store a token, use the OS keychain or the existing AES-256-GCM
  vault, scope it to read-only where possible, and never log it.
- Never ask for a broker **master password** or withdrawal permission.
- Never accept a third party's account credentials without a documented authority
  (and, for live trading, don't accept it at all without counsel).
- On offboarding, revoke tokens and delete them.

### 4.6 Regulatory note on execution

Order transmission is not automatically "just software". Depending on how you
market it, whether you receive transaction-based compensation, and whether you
hold out as executing, regulators may treat it as arranging, transmitting, or
brokerage. The strongest protections are:

- the user is the account owner and instructs each order;
- Eclipse does not hold client money;
- Eclipse does not receive per-trade compensation from the broker;
- Eclipse does not solicit specific trades;
- Eclipse does not exercise discretion;
- the broker is identified as the executing party.

If you add broker referral fees, copy-trading, or managed accounts, re-run the
analysis. Those features change the character of the business.

---

## 5. Data, privacy, and security

### 5.1 Roles: self-hosted vs hosted

| Model | Who is the controller? | What Eclipse owes |
|---|---|---|
| Self-hosted OSS | The user/operator is the controller | Clear docs, secure defaults, no hidden phone-home, a licence and security policy |
| Hosted single-tenant | The customer is the controller; Eclipse is a processor | DPA, subprocessor list, security commitments, data-return/deletion |
| Hosted multi-user | Eclipse is the controller for account data; the customer may be a controller for its own content | Privacy Notice, lawful basis, DSAR process, retention, breach response |
| Hybrid (local app + cloud sync) | Split by data set | A clear data map and a DPA that says who controls what |

Do not call yourself a processor if you decide why and how the data is used. Do
not call yourself a controller if you only host a customer's isolated instance.

### 5.2 Laws that can reach you

| Law | Trigger | Core obligations |
|---|---|---|
| GDPR | EU users, even if you are outside the EU | Lawful basis, notice, DSAR, retention, security, breach notification, DPIA, transfers, DPA |
| UK GDPR / DPA 2018 | UK users | Same core, plus ICO registration/fee where applicable |
| CCPA/CPRA | California consumers, revenue/threshold tests | Notice, deletion, correction, opt-out of sale/share, limits on sensitive data |
| Pakistan data protection | Users in Pakistan; framework still developing | Track the current law/regulations; apply GDPR-grade controls as a baseline |
| Sector rules | Financial data, broker data | Confidentiality, recordkeeping, outsourcing, incident notice |
| Contract | Your own Terms/DPA | Whatever you promised |

**Extraterritoriality is real.** "Our server is in Pakistan" does not remove GDPR
if you offer services to EU users or monitor their behaviour.

### 5.3 Data minimisation is the cheapest compliance

- Do not collect what you do not need.
- Do not store broker passwords.
- Do not store full account numbers if a masked identifier is enough.
- Do not send portfolio data to a model provider unless necessary and disclosed.
- Default to local models / local-only mode for sensitive work.
- Give users a real delete/export path.
- Set retention periods per data class, not "forever".

The existing data map (`docs/data-and-privacy.md`) is good. Turn it into a formal
record of processing activities and a retention schedule.

### 5.4 Security baseline

Aim for a documented, testable baseline, not a certificate:

- **Authentication**: strong password hashing (already scrypt), session expiry,
  MFA for hosted operator accounts, fail-closed when auth is misconfigured.
- **Authorisation**: least privilege, per-tenant isolation, operator-only routes.
- **Encryption**: TLS in transit; OS-level encryption at rest for self-hosted;
  AES-256-GCM for secrets; key rotation and separation.
- **Secrets**: no secrets in git; pre-commit scanning; env/secret manager; redact
  logs.
- **Dependencies**: lockfiles, audit, SBOM, timely patching.
- **App security**: OWASP ASVS Level 2 as a target; input validation; SSRF
  protection; safe deserialisation; rate limits.
- **Monitoring**: audit logs, anomaly alerts, incident runbook.
- **Testing**: unit/integration tests, a pre-launch penetration test for hosted
  live trading, and a retest after material changes.
- **Disclosure**: `SECURITY.md`, a private reporting channel, and a response SLA.

### 5.5 GDPR/hosted operational checklist

- [ ] Privacy Notice with purposes, lawful basis, categories, recipients,
      transfers, retention, rights, and contact.
- [ ] Records of processing activities.
- [ ] DPIA for live trading, profiling, and any AI processing.
- [ ] DPA with customers and a subprocessor list (hosting, models, email,
      monitoring).
- [ ] Standard contractual clauses / adequacy mechanism for transfers.
- [ ] DSAR and deletion procedure with identity verification.
- [ ] Retention schedule and automated deletion where possible.
- [ ] Breach response plan with a 72-hour decision path.
- [ ] Data-processing addendum in the Terms or a separate DPA.
- [ ] Vendor due diligence and DPAs with model/search/broker providers.
- [ ] Cookie/tracking notice (and consent where required).

### 5.6 Breach response

1. **Contain** - revoke sessions/tokens, isolate the host, preserve evidence.
2. **Assess** - what data, whose, how many, what harm, is it still ongoing?
3. **Notify internally** - founder/security lead/counsel; do not speculate
   publicly.
4. **Notify regulators** where required (GDPR: 72 hours after awareness, if
   likely risk).
5. **Notify affected users** where required, with clear facts and remediation.
6. **Remediate** - patch, rotate, retest.
7. **Record** - timeline, decisions, evidence, lessons.

Do not delete logs to "clean up". Do not pay an extortion demand without counsel
and law enforcement advice. Do not tell users "no data was accessed" until you
have verified it.

### 5.7 Credentials are the crown jewels

A stolen broker credential can cause direct financial loss and is far more
damaging than a leaked chat. Therefore:

- local attach / OAuth / short-lived tokens over stored passwords;
- read-only scopes unless trading is explicitly enabled;
- encryption with a key that is not in the same database;
- no credentials in prompts, logs, traces, memory, or error messages;
- rotation and revocation on offboarding;
- a "disconnect and revoke" button that actually works.

---

## 6. Open-source licensing and contributor protection

### 6.1 Licence choice

You currently use **MIT**. That is a reasonable default for adoption.

| Licence | Best for | Trade-offs |
|---|---|---|
| **MIT** | Maximum adoption, simplicity, minimal friction | No explicit patent grant; no trademark licence; no copyleft; silent on patents |
| **Apache 2.0** | Patent grant, enterprise comfort, explicit contribution terms | Slightly more ceremony; still permissive; no copyleft |
| **AGPL 3.0** | Preventing a closed hosted fork | Network copyleft; many companies refuse it; does not by itself create liability protection |
| **Dual licence** | Open core + commercial edition | Requires a CLA or clean copyright ownership; community trust work |
| **Source-available / Commons Clause** | Restricting commercial resale | **Not open source**; do not label it OSI-approved; can damage adoption |

**Recommendation:** keep MIT for the core unless patent risk in the quant/algo
space is a real concern, in which case Apache 2.0 is the better long-term choice.
Changing the licence requires the consent of contributors whose code is in the
tree (or a clean-room rewrite), so decide early.

**Do not use AGPL to try to solve liability.** AGPL is a copyright licence. It
does not make users responsible for losses and does not protect you from
negligence claims. It may, however, be appropriate for a separate hosted
component if your goal is to keep a network service open.

**Licence boundary:** the `pine-engine` already separates an AGPL dependency
(`pinets`) into a standalone program. Keep that boundary. Do not link AGPL code
into the MIT core without legal review.

### 6.2 What the licence does and does not do

| It does | It does not |
|---|---|
| Grant copyright permissions | Create a contract with hosted users |
| Disclaim warranty for the software | Disclaim liability for your hosted service, data handling, or personal conduct |
| Limit some contributor exposure | Prevent a regulator from applying financial law |
| Require notice retention | Protect the trademark or the project name |

For a hosted service, the **Terms of Service** are the user contract. The licence
is not.

### 6.3 Trademark and project identity

Add a **Trademark & Brand Policy**:

- the code is open; the name and logo are not;
- forks may not imply endorsement or use "BlackEclipse" as the product name;
- nominative fair use is allowed ("compatible with BlackEclipse");
- no use of the marks in a way that suggests a regulated status you do not have.

This is how you prevent a modified fork from damaging the project's reputation
without restricting the code.

### 6.4 DCO vs CLA

| | DCO | CLA |
|---|---|---|
| Friction | Low | Higher |
| Relicensing | Harder | Easier |
| Dual licensing | Awkward | Works |
| Contributor trust | High | Mixed |
| Best for | MIT/Apache community project | Commercial open-core |

**Recommendation:** DCO now. If you plan a proprietary edition, introduce a CLA
before accepting significant contributions, not after.

### 6.5 Contributor and maintainer protection

- Publish a **maintainer policy**: who decides, how, and what is not promised.
- Publish a **security policy** with a private channel and a disclosure window.
- Publish a **code of conduct** and enforce it consistently.
- Do not let contributors give personal warranties to users.
- Do not let a maintainer sign a contract with a broker or cloud provider
  personally.
- Keep the company as the contracting party for hosted services.
- Document that maintainers are not fiduciaries and owe no duty to users.
- Have a plan for a maintainer who leaves or is unavailable.

### 6.6 Third-party misuse

You cannot stop a fork from being used badly. You can:

- require the licence notice and disclaim warranty;
- protect the trademark;
- publish a clear "not affiliated / not endorsed" statement;
- avoid endorsing third-party deployments;
- keep a list of known-bad forks only if you must, and be factual;
- not promise support for modified versions.

---

## 7. Product-level compliance architecture

### 7.1 Principles

1. **Fail closed** on authorisation, credentials, and risk limits.
2. **Least privilege** for users, agents, tools, and brokers.
3. **Explicit consent** for every high-risk transition, recorded.
4. **Provenance** for data and model output, with `UNAVAILABLE` when unknown.
5. **Determinism** where possible; no invented fills or prices.
6. **Auditability** by default, not as an afterthought.
7. **No discretion, no custody, no pooling** as product invariants.
8. **User control** over accounts, credentials, limits, and orders.
9. **Honest marketing** that matches the product.
10. **Reversibility** for risk reduction (exits always available).

### 7.2 Capability matrix

| Capability | Default | Gate | Evidence | Status / action |
|---|---|---|---|---|
| Market data / charts | On | None | Data source, timestamp, freshness | Implemented |
| AI chat / research | On | Model configured | Run trace, citations, gate verdict | Implemented |
| Portfolio accounting | On | User data | Ledger entries, computed outputs | Implemented |
| Backtests / quant | On | User input | Dataset, code version, assumptions | Implemented |
| Paper trading | On | None | Paper ledger | Implemented |
| Broker read (account/positions) | Off | Connection + auth | Broker snapshot, sync state | Implemented |
| Demo order | Off | Approval or demo mandate | Order digest, approval, ledger | Implemented |
| Live order (manual) | **Off** | Arm + per-order typed phrase + approval | Arm event, digest, phrase, fill | Implemented; add acknowledgment |
| Unattended live (graph) | **Off** | Armed connection + workflow-pinned live mandate (<=24h) | Mandate, run id, node id, ledger | Implemented; add jurisdiction gate |
| Copy trading | **Not built** | Would require licensing review | - | Do not build without counsel |
| Discretionary management | **Not built** | Would require licensing | - | Do not build |
| Custody / pooled funds | **Not built** | Would require licensing | - | Do not build |
| Performance fees | **Not built** | Would require licensing | - | Do not build |
| Signal marketplace | **Not built** | Advice/financial promotion review | - | Do not build without counsel |
| Data export / delete | On | User request | Audit log | Implemented; add retention policy |
| Plugin / MCP tools | Off by default | Explicit install/trust | Tool call audit | Implemented; add warnings |

### 7.3 Onboarding flow (recommended)

1. **Age and capacity** - confirm 18+ and legal capacity.
2. **Jurisdiction** - select country; if restricted, block hosted trading and
   explain why.
3. **Experience** - optional self-declaration (not a suitability assessment).
4. **Risk acknowledgment** - short, specific, versioned; not buried.
5. **Terms / Privacy / AUP** - separate clickwrap acceptance; log version.
6. **AI disclosure** - explain what the AI is and is not.
7. **Demo-first** - encourage paper trading before live.
8. **Broker connection** - attest ownership and authority; explain local attach.
9. **Live enablement** - a second, explicit step; show the risks and the controls.
10. **Arming** - the existing typed phrase and time box.
11. **First order** - preview, worst-case risk, typed confirmation.
12. **Post-trade** - show broker-confirmed state and a link to the ledger.

### 7.4 UI copy rules

- Say **"analysis"**, **"scenario"**, **"estimate"**, **"hypothetical"** where
  accurate.
- Never say **"will"**, **"guaranteed"**, **"safe"**, **"accurate"** about a
  forecast.
- Say **"you are about to send an order to your broker"**, not "we are trading
  for you".
- Say **"the broker reports"**, not "the position is" when the state is unknown.
- Show **`UNAVAILABLE`** rather than a fake number.
- Show **source and timestamp** next to market data.
- Show **`COMPUTED` / `SOURCED` / `UNVERIFIED`** next to actionable claims.
- Show **"not financial advice"** at the point of analysis, not only in the
  footer.
- Show **"verify at your broker"** after an ambiguous order result.

### 7.5 Audit trail schema

For every material action, retain:

| Field | Example |
|---|---|
| Event id / timestamp | UUID, UTC |
| Actor | user id, session, IP, user agent |
| Action | `order.preview`, `order.submit`, `live.arm`, `mandate.create`, `ai.answer` |
| Resource | connection id, order id, run id, workflow version |
| Inputs | exact order intent, prompt hash, parameters |
| Model / code version | provider, model, code commit, node version |
| Data snapshot | source, timestamp, freshness, dataset hash |
| Authorisation | approval id, digest, typed phrase result, mandate id |
| Outcome | broker retcode, fill, error, `unknown` |
| Disclosure version | Terms/Risk/AI version accepted |

Store it append-only or hash-chained (the security audit already is). Retain long
enough for the limitation period in your key jurisdictions; 6-7 years is a
common commercial default, but minimise personal data and delete what you do not
need.

### 7.6 Feature flags and kill switches

- Global kill switch for hosted trading.
- Per-connection kill switch (implemented).
- Per-jurisdiction feature flag.
- Per-user trading suspension.
- Model/provider kill switch (fall back to `UNAVAILABLE`, not a fake answer).
- Data-provider kill switch (show stale/unavailable).
- A "disable all live trading now" operator action with an audit entry.

### 7.7 Do-not-build list (without licensed advice)

- Discretionary managed accounts.
- Copy-trading / mirror-trading.
- Pooled funds or model portfolios managed for clients.
- Performance fees or profit shares.
- Custody of client money or securities.
- Lending, margin provision, or payment services.
- Signal marketplaces with compensation.
- Personalized "you should buy" recommendations at scale.
- Any feature that implies a guarantee or a fiduciary relationship.

---

## 8. Required legal documents

### 8.1 Document register

| # | Document | Audience | Priority | Must contain | DIY or counsel |
|---|---|---|---|---|---|
| 1 | **Terms of Service** | Hosted users | P0 | Acceptance, eligibility, service description, no advice, risk, trading, data, IP, disclaimers, liability, indemnity, termination, disputes | Counsel review strongly advised |
| 2 | **Privacy Notice** | Hosted users | P0 | Data map, purposes, lawful basis, recipients, transfers, retention, rights, contact, cookies | Draft yourself, review for GDPR |
| 3 | **Risk Disclosure** | All users | P0 | Market risk, leverage, loss > deposit, liquidity, execution, slippage, outages, AI/model risk, no guarantee | Draft + counsel review |
| 4 | **Financial Disclaimer** | All users | P0 | Not advice, not a fiduciary, no suitability assessment, no guarantee, verify | Draft + counsel review |
| 5 | **AI Usage Disclosure** | All users | P0 | Probabilistic output, hallucinations, data limits, model changes, human review, no auto-reliance | Draft yourself |
| 6 | **Software Licence** | Everyone | P0 | MIT (current) or Apache 2.0; warranty disclaimer; liability limitation | Use the standard text |
| 7 | **Contributor Policy + DCO** | Contributors | P0 | Inbound=outbound, sign-off, no warranty, review, conduct | Use the standard DCO |
| 8 | **Acceptable Use Policy** | Hosted users | P0 | No unlawful trading, market abuse, third-party accounts, credential sharing, scraping, resale, malware | Draft + review |
| 9 | **Automated Trading Disclaimer** | Live users | P0 | User authorises each order, no discretion, broker executes, outages/bugs possible, kill switch, verify | Counsel review |
| 10 | **Data Processing Agreement** | Hosted business customers | P1 | Roles, instructions, subprocessors, security, breach, deletion, audits, transfers | Counsel template |
| 11 | **Security & Vulnerability Disclosure Policy** | Researchers | P0 | Scope, channel, SLA, safe harbour, out-of-scope | Already have `SECURITY.md`; extend |
| 12 | **Trademark & Brand Policy** | Community | P1 | Code is open; marks are not; fork naming; no endorsement | Draft yourself |
| 13 | **Cookie / Tracking Notice** | Hosted users | P1 | Categories, consent, analytics, opt-out | Draft + review |
| 14 | **Subprocessor List** | Hosted customers | P1 | Vendors, purpose, location, safeguards | Maintain |
| 15 | **Incident Response Policy** | Internal | P1 | Severity, roles, notification, evidence, communications | Draft + tabletop |
| 16 | **Complaints & Dispute Policy** | Users | P1 | Channel, acknowledgment, investigation, timeline, escalation | Draft + review |
| 17 | **Records Retention Policy** | Internal | P1 | Data classes, periods, legal hold, deletion | Draft + review |
| 18 | **Sanctions & Export Policy** | Internal | P2 | Restricted countries, screening, blocking, escalation | Counsel |
| 19 | **Contributor Code of Conduct** | Community | P2 | Standards, enforcement, reporting | Use Contributor Covenant |
| 20 | **Regulatory Status Statement** | Users/investors | P2 | What Eclipse is and is not; no licence held; jurisdiction limits | Counsel review |

### 8.2 The minimum viable pack

**For the open-source, self-hosted project (today):**

1. `LICENSE` (MIT, already present).
2. `SECURITY.md` (already present; extend the safe-harbour language).
3. `CONTRIBUTING.md` + `DCO`.
4. `README` notice: "research and order-entry software; not financial advice; you
   are responsible for your decisions; no warranty".
5. In-app first-run notice.

**For the hosted service (before taking a single real user):**

1. Terms of Service.
2. Privacy Notice.
3. Risk Disclosure.
4. Financial Disclaimer.
5. AI Usage Disclosure.
6. Acceptable Use Policy.
7. Automated Trading Disclaimer (if live trading is enabled).
8. DPA (if business customers).
9. Security policy.
10. Complaints/incident contact.

Do not launch a hosted service with only a footer disclaimer.

### 8.3 Copy-ready core notice

**Short version (footer, README, about page):**

> BlackEclipse is self-directed research and order-entry software. It is not a
> broker, investment adviser, portfolio manager, or fiduciary. It does not manage
> your account, guarantee results, or share your profits or losses. AI output and
> market data can be wrong, incomplete, or delayed. You are responsible for your
> decisions, your risk, and your compliance with your broker and local law.

**First-run acknowledgment (modal):**

> **Before you use Eclipse**
>
> Eclipse helps you research markets, test ideas, and send orders to your own
> broker. It does not make decisions for you and does not promise that any
> analysis, model, or trade will be profitable.
>
> - Markets can move against you. Leveraged trading can lose more than you
>   deposit.
> - AI outputs can be wrong or fabricated. Verify prices, orders, and positions
>   with your broker.
> - You must own or be authorised to trade the account you connect.
> - You are responsible for position sizing, risk limits, and compliance with
>   your local law.
> - Eclipse is not liable for your trading losses, except where the law says
>   otherwise.
>
> [ ] I have read and accept the Terms, Privacy Notice, and Risk Disclosure.
> [ ] I understand that Eclipse is not financial advice.

**Live-trading acknowledgment (separate, stronger):**

> **You are enabling live trading**
>
> Live orders can lose real money. Eclipse will transmit the exact order you
> authorise to your broker; the broker executes it. Fills, slippage, rejections,
> and outages are outside Eclipse's control. If a result is unclear, check your
> broker immediately; Eclipse will not retry an ambiguous order.
>
> You confirm that you own or are authorised to trade this account, that you will
> set and enforce your own risk limits, and that you understand you can lose more
> than you deposit.
>
> Type **ENABLE LIVE TRADING** to continue.

### 8.4 Document governance

- Version every document (`2026-11-07` or `v1.0`).
- Store the accepted version, timestamp, user id, IP, and user agent.
- Re-prompt on material changes; do not silently update.
- Keep an archive of prior versions.
- Translate the core notices into the languages you actively support; do not rely
  on machine translation for legal terms without review.
- Make the documents linkable and printable.
- Keep the Privacy Notice consistent with the actual data map.

---

## 9. Incident management and dispute resolution

### 9.1 Incident taxonomy

| Type | Examples | First owner |
|---|---|---|
| Trading loss / unexpected order | Wrong size, duplicate order, failed exit, stale price | Trading lead + founder |
| Software bug | Crash, wrong calculation, broken gate | Engineering |
| Outage | Broker disconnected, runtime down, data provider down | Operations |
| Data breach | Credential leak, database exposure, prompt leak | Security lead |
| AI failure | Hallucinated fact, bad recommendation, unsafe output | AI/engineering |
| Regulatory inquiry | Letter from SECP/FCA/SEC/CFTC/ICO | Founder + counsel |
| IP claim | DMCA, licence breach, trademark | Founder + counsel |
| Fraud / abuse | Stolen account, market manipulation, scam | Security + counsel |

### 9.2 First 24 hours

1. **Stop the harm** - use the kill switch, revoke sessions/tokens, disable the
   feature, roll back if safe.
2. **Preserve evidence** - logs, order ledger, approvals, mandates, arm events,
   market data snapshots, model/config, code version, support messages. Do not
   edit or delete.
3. **Open an incident record** - id, time, reporter, scope, severity, decisions.
4. **Notify the right people** - founder, security, counsel, insurer (as
   required). Do not admit liability in writing.
5. **Communicate facts, not guesses** - tell affected users what you know, what
   you are doing, and when you will update.
6. **Do not pay or promise** - no settlement, refund, or admission without
   counsel.

### 9.3 Evidence to retain

- The exact order intent, digest, approval, typed phrase result, arm/mandate,
  broker retcode, fill, and reconciliation state.
- The run id, workflow version, agent preset, model/provider, prompt hash, tool
  calls, and output.
- The market data source, timestamp, freshness, and dataset hash.
- The user's acceptance of the Terms/Risk/AI version, IP, session, and device.
- Support tickets, emails, screenshots, and call notes.
- System health, deploy version, and incident timeline.
- Any broker statement or confirmation the user provides.

### 9.4 Investigation

- Establish a timeline from independent sources, not memory.
- Determine whether the cause was Eclipse, the broker, the data provider, the
  model provider, the user, or an external event.
- Check whether a control failed or was bypassed.
- Check whether the user authorised the exact action.
- Document the root cause and the fix.
- Decide whether the incident is notifiable (privacy, financial, regulatory).
- Do not destroy the incident record after closing; retain it per policy.

### 9.5 Complaints and legal notices

- Publish a **complaints channel** (email/form) and an acknowledgment target
  (e.g. 2 business days) and a substantive response target (e.g. 10 business
  days).
- Log every complaint with the same evidence standard as an incident.
- Escalate to counsel on: threats of litigation, regulator contact, media,
  class-action language, large losses, or allegations of fraud.
- Preserve documents immediately on notice of a dispute (litigation hold).
- Do not respond emotionally or speculate about fault.
- Consider a without-prejudice settlement discussion only with counsel.

### 9.6 Dispute resolution clauses

| Option | Pros | Cons |
|---|---|---|
| Courts of the company's home country | Familiar, predictable | Foreign users may not be bound; enforcement abroad |
| Arbitration (e.g. LCIA, ICC, SIAC) | Cross-border enforceability; privacy | Costly for small claims; consumer clauses may be unenforceable |
| User's local courts | Consumer-friendly | You may have to defend abroad |
| Class-action waiver | Limits aggregate exposure (US) | Frequently challenged; not enforceable everywhere |
| EU/UK consumer forum | Required for consumers in practice | You cannot contract out of local consumer rights |

**Recommendation:** choose the company's home courts for business users; for
consumers, do not pretend you can exclude their local mandatory rights. Add a
carve-out for small claims and injunctive relief. Get the clause reviewed in your
main markets.

### 9.7 Tabletop exercise

Before live trading, run one 90-minute exercise:

- A user says "your bot opened 10 lots without permission and I lost $50k."
- A broker token is leaked.
- A regulator asks what advice the AI gave.
- A model provider changes terms or has an outage.

Write down who does what, what evidence you pull, and what you say. Fix the gaps.

---

## 10. Implementation roadmap

### 10.1 Phase 0 - immediate (0-30 days, USD 0-3,000)

| # | Action | Owner | Cost | Essential? |
|---|---|---|---|---|
| 1 | Incorporate (or confirm entity) and assign IP | Founder | 100-1,500 | Yes |
| 2 | Open business bank account; separate finances | Founder | 0-300 | Yes |
| 3 | Publish Risk Disclosure + Financial Disclaimer + AI Disclosure + AUP | Founder | 0-500 (draft) | Yes |
| 4 | Add clickwrap acceptance + version logging | Engineering | 1-3 days | Yes |
| 5 | Add the live-trading acknowledgment modal | Engineering | 1-2 days | Yes |
| 6 | Add jurisdiction/ownership attestation | Engineering | 2-5 days | Yes |
| 7 | Add `DCO`, trademark policy, and README notice | Founder | 0-300 | Yes |
| 8 | Confirm no secrets in git; run security preflight | Engineering | 0 | Yes |
| 9 | Create an incident/complaints inbox and a simple log | Founder | 0 | Yes |
| 10 | Freeze marketing claims that imply guaranteed returns | Founder | 0 | Yes |

**Deliverable:** a user cannot reach live trading without a recorded, specific
acknowledgment, and the project has a real legal person behind it.

### 10.2 Phase 1 - pre-launch (1-3 months, USD 5,000-20,000)

| # | Action | Owner | Cost | Essential? |
|---|---|---|---|---|
| 1 | Lawyer review of Terms, Privacy, Risk, Trading Disclaimer | Counsel | 2,000-8,000 | Yes |
| 2 | GDPR/UK GDPR review + DPA template (if hosted) | Counsel | 1,000-4,000 | Yes for EU/UK |
| 3 | Security review / pen test of hosted live trading | Vendor | 3,000-15,000 | Yes for hosted |
| 4 | Insurance quotes: tech E&O + cyber; D&O if funded | Broker | 2,000-10,000/yr | Strongly advised |
| 5 | Incident response runbook + tabletop | Founder/eng | 0-2,000 | Yes |
| 6 | Retention schedule + delete/export flows | Engineering | 2-5 days | Yes |
| 7 | Restricted-jurisdiction policy + geo-controls | Engineering | 2-5 days | Yes |
| 8 | Subprocessor list + vendor DPAs | Founder | 0-1,000 | If hosted |
| 9 | Complaint handling policy + SLA | Founder | 0-500 | Yes |
| 10 | Trademark filing (at least in the home market) | Counsel/agent | 300-1,500 | Recommended |

**Deliverable:** a hosted launch with a reviewed contract pack, a tested incident
path, insurance, and a documented data lifecycle.

### 10.3 Phase 2 - post-launch (3-12 months, USD 10,000-60,000+)

| # | Action | Cost | When |
|---|---|---|---|
| 1 | Outside counsel retainer / on-call | 1,000-5,000/mo | When revenue or live volume grows |
| 2 | SOC 2 readiness or ISO 27001 gap assessment | 15,000-60,000 | Enterprise customers demand it |
| 3 | Bug bounty / continuous security testing | 2,000-15,000/yr | After a stable hosted base |
| 4 | Formal compliance monitoring (regulatory changes) | 2,000-10,000/yr | When targeting multiple countries |
| 5 | D&O insurance | 3,000-20,000/yr | When funded or board formed |
| 6 | Local law reviews for new markets | 1,000-5,000 each | Before targeting |
| 7 | Annual contract and incident review | 2,000-8,000 | Yearly |
| 8 | Accessibility/localisation of notices | 1,000-5,000 | When expanding |

### 10.4 Essential vs optional vs defer

| Priority | Items |
|---|---|
| **Essential** | Entity + IP assignment, Terms/Privacy/Risk/AI/AUP, clickwrap + version log, live-trading acknowledgment, jurisdiction/ownership attestation, no-discretion invariant, audit evidence, security baseline, incident contact |
| **Strongly advised** | Counsel review, insurance, pen test, DPA, retention/deletion, complaints policy, trademark |
| **Optional / later** | SOC 2, ISO 27001, bug bounty, formal compliance officer, multi-jurisdiction reviews, arbitration optimisation |
| **Do not defer** | Live-trading consent, entity separation, privacy notice, credential handling |

### 10.5 What a bootstrapped project can realistically do itself

You can draft and ship:

- the core notices and the first-run modal;
- the clickwrap/version logging;
- the data map and retention schedule;
- the incident log and complaint intake;
- the DCO and contributor policy;
- the security baseline and disclosure policy;
- the audit queries that reconstruct an order.

You should not DIY:

- the legal characterisation of your activity in a new country;
- the Terms' liability/indemnity/dispute architecture;
- the DPA and international transfer mechanism;
- the response to a regulator or a lawsuit;
- the insurance coverage analysis;
- a licence change or a dual-licensing structure.

### 10.6 Triggers to get counsel immediately

- You receive a legal notice, regulator letter, or media inquiry about losses.
- You plan to enable live trading in a new country.
- You add copy-trading, managed accounts, pooled funds, performance fees, or
  custody.
- You raise money, take on a co-founder, or grant equity.
- You suffer a breach involving credentials or financial data.
- A broker or data provider terminates you or changes terms.
- You want to change the licence or adopt a CLA.
- You cross USD 1m in trading volume or 10,000 hosted users, whichever comes
  first.

### 10.7 A 90-day sequence

**Weeks 1-2:** entity, IP assignment, bank account, document owners, marketing
freeze.

**Weeks 3-4:** draft the core pack; build the clickwrap and live-trading modal;
add jurisdiction and ownership attestations.

**Weeks 5-6:** counsel review; privacy/GDPR review; incident runbook; data
retention.

**Weeks 7-8:** pen test; insurance quotes; DPA; complaint process; tabletop.

**Weeks 9-10:** fix findings; re-test; update docs; train support.

**Weeks 11-12:** limited launch; monitor; review every incident; publish the
security and complaints channels.

---

## 11. Jurisdiction-specific uncertainty register

Track these as open questions. Do not let a confident-sounding answer in this
document substitute for local advice.

| # | Question | Why uncertain | Provisional position | Action |
|---|---|---|---|---|
| 1 | Is AI-generated, portfolio-aware analysis "investment advice" in the UK/EU? | Personalisation + actionable language can trigger MiFID/FCA advice | Treat as general information only; avoid "you should" and suitability inputs | Local counsel before marketing to UK/EU |
| 2 | Does order transmission make Eclipse a broker? | Depends on solicitation, compensation, custody, and holding out | User-owned account, user instruction, no transaction-based compensation | Counsel if adding referral fees or copy-trading |
| 3 | Is MT5 retail forex/CFD activity restricted for retail users in the user's country? | Leverage caps and retail restrictions vary | Jurisdiction attestation; do not solicit restricted markets | Local review per market |
| 4 | Does the US publisher's exclusion cover an interactive AI? | The exclusion is fact-specific and narrow | No personalised recommendations; keep output impersonal | US counsel before US marketing |
| 5 | Does Pakistan's developing data law apply, and with what obligations? | Framework still evolving | Apply GDPR-grade baseline | Track and review |
| 6 | Is a hosted service in Pakistan a licensed SECP/SBP activity? | Depends on advice, custody, and execution | No custody, no discretion, no solicitation | SECP/SBP counsel before hosting Pakistani clients |
| 7 | Is the EU AI Act transparency/high-risk classification triggered? | Application depends on use and role | Disclose AI interaction; avoid high-risk uses | Counsel before credit/insurance use cases |
| 8 | Are consumer waivers enforceable in each market? | EU/UK/Pakistan consumer law can void unfair terms | Do not rely on a total waiver; allocate risk clearly | Review in each consumer market |
| 9 | Can a foreign judgment or arbitral award be enforced? | Depends on treaties and the defendant's assets | Home courts for business users; arbitration for cross-border | Counsel |
| 10 | Does DORA apply to a hosted service? | Depends on customer type and criticality | Contractual security/exit terms; monitor | Enterprise/regulated customers only |
| 11 | Are sanctions/export controls triggered? | Restricted territories and persons | Basic screening + geo-block; no direct sales to restricted regions | Counsel if scaling |
| 12 | Does the open-source licence expose maintainers? | Licence disclaims warranty but not tort/fraud | DCO, no personal warranties, security process | Review on any licence change |

**Rule:** when a new market or feature is uncertain, ship the lower-risk version
first (research/demo only), document the decision, and get advice before enabling
live trading or payments there.

---

## Appendix A - Copy-ready notices

### A.1 README / footer

> **Not financial advice.** BlackEclipse is self-directed research and
> order-entry software. It is not a broker, investment adviser, portfolio
> manager, or fiduciary. It does not manage your account, guarantee results, or
> share your profits or losses. AI output and market data can be wrong,
> incomplete, or delayed. You are responsible for your decisions, your risk, and
> your compliance with your broker and local law.

### A.2 AI output label

> AI-generated analysis. Probabilistic, may be incomplete or wrong, and not a
> recommendation. Verify with your own research and your broker. Past performance
> and backtests do not predict future results.

### A.3 Backtest label

> Hypothetical, simulated results. Based on historical data and stated
> assumptions; does not include all real-world costs, slippage, or taxes unless
> shown. Not a track record and not a promise of future performance.

### A.4 Trade confirmation label

> You are about to send this exact order to your broker. Check the symbol, side,
> size, price, stop, and target. The broker may reject, partially fill, or fill at
> a different price. Eclipse does not guarantee execution.

### A.5 Data freshness label

> Source: [provider]. Observed: [timestamp]. Retrieved: [timestamp]. Status:
> live / delayed / stale / historical / unavailable. [If stale: this is not a
> current price.]

### A.6 Incident communication (first response)

> We are aware of [incident] affecting [scope]. We have [contained/disabled X] and
> are investigating. We will update you by [time]. Please do not [action] until
> we confirm. If you believe you have suffered a loss, contact [channel] with
> [details]. This is an initial notice; facts may change as we investigate.

---

## Appendix B - Evidence retention matrix

| Evidence | Minimum retention | Why |
|---|---|---|
| Terms/Privacy/Risk acceptance (version, time, IP) | Life of account + 6 years | Consent and contract proof |
| Order intent, approval, digest, phrase result | 6-7 years | Dispute and regulatory |
| Arm/mandate events | 6-7 years | Authority chain |
| Broker ledger, fills, reconciliation | 6-7 years | Execution truth |
| AI run trace, model/provider, prompt hash | 2-6 years (minimise) | Explain output |
| Market data snapshot/provenance | 2-6 years | Reconstruct decision context |
| Security audit log | 1-6 years | Incident investigation |
| Support tickets/complaints | 6 years after closure | Dispute history |
| Incident records | 6-7 years | Regulatory/insurance |
| Marketing materials and versions | 6 years | Misrepresentation defence |
| Licence/contribution records | Permanent | IP chain |

Adjust to local limitation periods and privacy minimisation. Do not keep
credentials or unnecessary personal data just because storage is cheap.

---

## Appendix C - Brief for counsel

Send this to a lawyer to make the first meeting efficient:

1. **Entity and IP:** Is our structure appropriate? Are all IP assignments
   complete? Any personal liability gaps?
2. **Characterisation:** On the facts (no discretion, no custody, user-owned
   broker, user authorises each order), are we providing advice, arranging,
   brokerage, or software in [country]?
3. **Documents:** Review our Terms, Privacy, Risk Disclosure, AI Disclosure,
   Trading Disclaimer, AUP, and DPA. Identify unenforceable clauses.
4. **Cross-border:** Which countries can we market to? What must we geo-block?
5. **Consumer law:** Which disclaimers/liability caps are enforceable?
6. **AI:** Does the AI Act or local AI rules apply? What transparency is required?
7. **Data:** Are we controller or processor? Is our DPA/transfer mechanism valid?
8. **Disputes:** What governing law/forum should we use? Is arbitration worth it?
9. **Insurance:** What coverage should we carry?
10. **Incident:** What are our notification duties if credentials or financial data
    leak?

---

## Appendix D - Glossary

| Term | Meaning here |
|---|---|
| **Controller** | The party that decides why and how personal data is processed |
| **Processor** | A party that processes data on the controller's instructions |
| **MiFID II** | EU framework for investment firms, advice, and execution |
| **FCA** | UK Financial Conduct Authority |
| **SEC** | US Securities and Exchange Commission |
| **CFTC** | US Commodity Futures Trading Commission |
| **SECP** | Securities and Exchange Commission of Pakistan |
| **SBP** | State Bank of Pakistan |
| **CTA/CPO** | Commodity Trading Advisor / Commodity Pool Operator (US) |
| **Publisher's exclusion** | US doctrine that can protect impersonal general publishing from adviser registration |
| **DCO** | Developer Certificate of Origin |
| **CLA** | Contributor Licence Agreement |
| **DPA** | Data Processing Agreement |
| **DSAR** | Data Subject Access Request |
| **DPIA** | Data Protection Impact Assessment |
| **E&O** | Errors and omissions insurance |
| **D&O** | Directors and officers insurance |
| **Clickwrap** | Acceptance by clicking a button, with a recorded log |
| **Browsewrap** | A notice merely linked on a page; weaker or unenforceable |
| **Hypothetical performance** | Simulated/backtested results, not actual trading |

---

## Related docs

- [`docs/fiduciary-advice.md`](../fiduciary-advice.md) - the Advisory Gate and
  ledger that make "computed vs unverified" real.
- [`docs/trading.md`](../trading.md) - broker connectivity, arming, approvals,
  mandates, risk limits, reconciliation.
- [`docs/data-and-privacy.md`](../data-and-privacy.md) - data map, vault, local
  models, wipe.
- [`docs/harness/security.md`](../harness/security.md) - the security decision path.
- [`SECURITY.md`](../../../SECURITY.md) - vulnerability disclosure.
- [`CONTRIBUTING.md`](../../CONTRIBUTING.md) - contributor process.
- [`LICENSE`](../../LICENSE) - MIT licence text.
- [`docs/legal/README.md`](./README.md) - document register and status.
