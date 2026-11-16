# CFA Level I — Derivatives and Risk Management

> **Not affiliated with CFA Institute.** These are original study notes, not CFA Institute materials. "CFA" is a trademark of CFA Institute. See `../CFA-NOTICE.md`.

**Weight 6-9% (was 5-8%) · 10 modules · ninth in the study order.** Renamed from
*Derivatives* in 2027 and slightly up-weighted. Concept-light at Level I: the exam
asks for payoff, price and value mechanics, not exotic models.

## Learning modules (official 2027)

| # | Module | Focus |
|---|---|---|
| 1 | Derivative Instrument and Derivative Market Features | Define a derivative; basic features; **OTC vs exchange-traded** markets |
| 2 | Forward Commitment and Contingent Claim Features and Instruments | Forward, futures, swaps, options (calls and puts), credit derivatives; **value at expiration and profit from long/short calls and puts**; forward commitments vs contingent claims |
| 3 | Derivative Benefits, Risks, and Issuer and Investor Uses | Benefits and risks; how issuers and investors differ in use |
| 4 | Arbitrage, Replication, and the Cost of Carry | Arbitrage and replication in pricing; **spot vs expected future price**; **cost of carry** |
| 5 | Pricing and Valuation of Forward Contracts | Value and price at initiation, during life, and at expiration; **forward rates for interest rate forwards** and their uses |
| 6 | Pricing and Valuation of Futures Contracts | Forward vs futures value and price; why the prices differ |
| 7 | Pricing and Valuation of Interest Rate and Other Swaps | Swaps as a series of forwards; **value vs price of a swap** |
| 8 | Pricing and Valuation of Options | **Exercise value, moneyness and time value**; arbitrage vs replication for contingent claims; **factors determining option value** |
| 9 | Option Replication Using Put-Call Parity | **Put-call parity** for European options; **put-call forward parity** |
| 10 | Valuing a Derivative Using a One-Period Binomial Model | The one-period binomial valuation; **risk neutrality** in derivatives pricing |

## What to learn first

1. **Modules 1-3** (features, instruments, uses) — vocabulary.
2. **Module 2's payoff arithmetic** — option payoffs and profits; the most reliably
   examined calculation in the topic.
3. **Modules 4-7** (cost of carry, forwards, futures, swaps) — one coherent pricing
   family; learn together.
4. **Modules 8-10** (options, parity, binomial) — the option core.

## Tier 1 — must memorise

- **Option payoff and profit** for long/short call and put, at expiration and
  before. **Profit = payoff - premium paid.**
- **Moneyness:** in-, at- and out-of-the-money by strike vs underlying for calls
  and puts.
- **Intrinsic (exercise) value** and **time value** = option price - intrinsic.
- **Put-call parity:** C + PV(X) = P + S (European options). Know the rearrangement
  for each of the four instruments.
- **Put-call forward parity** (the version replacing the bond with a forward).
- **Forward price with cost of carry:** F = S(1 + r)^T adjusted for carry costs and
  benefits (dividends, storage).
- **Value of a forward at expiry** = spot - forward price (long position), with the
  sign flipped for short.
- **Swap as a series of forwards**, and the value/price distinction.
- **One-period binomial:** the risk-neutral probability p, then the expected
  payoff discounted at the risk-free rate.

## Tier 2 — must understand

- Why forward and futures prices differ (marking to market, interest rate
  uncertainty).
- Arbitrage and replication as the single idea behind every pricing formula.
- Why an option's value rises with volatility and time to expiry but the
  underlying's expected return does not enter directly.
- Risk neutrality: why we can price without knowing investor preferences.
- Why the swap value is zero at initiation.

## Common traps

- **Confusing price and value** for forwards and swaps — the price is fixed at
  initiation; the value moves. This distinction is examined repeatedly.
- Forgetting to **discount the strike** in put-call parity (using X instead of
  PV(X)).
- **Profit vs payoff** — a profitable-looking payoff can still be an overall loss
  once the premium is subtracted.
- Getting the **long/short sign backwards** in the expiration value.
- Mixing up **which position benefits** from a fall in the underlying (long put and
  short call).
- Applying put-call parity to **American options** — it holds for European.
- Treating **cost of carry as only the interest rate** when dividends or storage
  costs are present.
- Assuming a **higher expected return on the underlying raises the option value**
  — in the risk-neutral framework it does not enter.
- Forgetting that **the binomial probability is risk-neutral**, not the true
  probability.

## Typical question patterns

- Compute the payoff and profit of an option position at expiry, given strike and
  premium.
- Identify whether an option is in-, at- or out-of-the-money.
- Use put-call parity to solve for the missing leg (a very common item).
- Compute a forward price with a dividend and state the arbitrage profit if the
  market price differs.
- Value a swap as a series of forwards.
- Compute a one-period binomial option value and state the risk-neutral
  probability.

## Free resources for this topic

- Official curriculum and topic questions: the Learning Ecosystem.
- Learning outcomes: the free 2027 Level I Topic Outlines PDF.
- Video supplement: a free Level I derivatives segment.
- Question volume: a free Level I question bank.

## Practice target and revisits

- **120-160 questions**, weighted toward put-call parity and payoffs.
- Revisit twice; derivatives formulas are short but easy to mis-sign.

## Dependencies

- Needs: discounting and TVM from Quantitative Methods; the rate conventions from
  Fixed Income for forwards and swaps.
- Feeds: nothing downstream.

## Failure handling

- An option question that does not state whether it is European or American ->
  state the assumption; put-call parity requires European.
