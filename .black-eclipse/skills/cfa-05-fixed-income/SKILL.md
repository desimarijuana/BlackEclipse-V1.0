# CFA Level I — Fixed Income

> **Not affiliated with CFA Institute.** These are original study notes, not CFA Institute materials. "CFA" is a trademark of CFA Institute. See `../CFA-NOTICE.md`.

**Weight 11-14% · 19 modules (the most of any topic) · fifth in the study order.**
The module count overstates the difficulty — many modules are descriptive — but
the duration, convexity, yield and credit modules are heavily computational.

## Learning modules (official 2027)

| # | Module | Focus |
|---|---|---|
| 1 | Fixed-Income Instrument Features | Bond features; the **indenture**; affirmative vs negative covenants |
| 2 | Fixed-Income Cash Flows and Types | Cash flow structures; **contingency provisions** favouring issuer vs investor; legal, regulatory and tax considerations |
| 3 | Fixed-Income Issuance and Trading | Market segments and participants; fixed-income index types; primary/secondary markets vs equities |
| 4 | Fixed-Income Markets for Corporate Issuers | Short-term funding alternatives; **repurchase agreements** (uses, benefits, risks); investment-grade vs high-yield long-term funding |
| 5 | Fixed-Income Markets for Government Issuers | Sovereign vs non-sovereign; quasi-government and supranational agencies; government vs corporate issuance |
| 6 | Fixed-Income Bond Valuation: Prices and Yields | **Price from yield on or between coupon dates**; the price/coupon/maturity/yield relationships; matrix pricing |
| 7 | Yield and Yield Spread Measures for Fixed-Rate Bonds | Annual yield for varying compounding; **yield and yield spread measures** (current yield, YTM, yield to call, spread measures) |
| 8 | Yield and Yield Spread Measures for Floating-Rate Instruments | **Floating-rate spread measures**; money market yield measures |
| 9 | The Term Structure of Interest Rates | **Spot, par and forward curves**; price a bond from spot rates; par and forward rates from each other; compare the three curves |
| 10 | Interest Rate Risk and Return | Sources of return from a fixed-rate bond; holding period return vs Macaulay duration vs investment horizon; **Macaulay duration** |
| 11 | Yield-Based Bond Duration Measures and Properties | **Modified duration, money duration, PVBP**; how maturity, coupon and yield level affect interest rate risk |
| 12 | Yield-Based Bond Convexity and Portfolio Properties | **Convexity and the convexity adjustment**; price change from duration and convexity; portfolio duration and convexity and their limits |
| 13 | Curve-Based and Empirical Fixed-Income Risk Measures | **Effective duration and effective convexity** for bonds with embedded options; **key rate duration**; empirical vs analytical duration |
| 14 | Credit Risk | Components of credit risk: **probability of default and loss given default**; credit ratings and their limits; factors driving yield spreads |
| 15 | Credit Analysis for Government Issuers | Special considerations for sovereign and non-sovereign issuers |
| 16 | Credit Analysis for Corporate Issuers | Qualitative and quantitative credit factors; **credit ratios**; seniority, secured vs unsecured, priority of claims |
| 17 | Fixed-Income Securitization | Benefits of securitization; the parties and their roles |
| 18 | Asset-Backed Security (ABS) Instrument and Market Features | Covered bonds; **credit enhancement structures**; non-mortgage ABS types, cash flows and risks; **CDOs** |
| 19 | Mortgage-Backed Security (MBS) Instrument and Market Features | **Prepayment risk** and time tranching; residential mortgage loan features; **pass-throughs and CMOs**; commercial MBS |

## What to learn first

1. **Modules 1-5** (features, markets) — descriptive; read fast.
2. **Modules 6-9** (valuation, yields, term structure) — the pricing core and a
   prerequisite for everything after it.
3. **Modules 10-13** (duration, convexity, curve-based risk) — the heaviest
   calculation load and the most reliably examined block.
4. **Modules 14-16** (credit) — ratio-driven and conceptual.
5. **Modules 17-19** (securitization) — descriptive; learn ABS and MBS as a pair.

## Tier 1 — must memorise

- **Bond price** from yield: the present value of coupons plus principal, with the
  full-period form and the between-coupon-dates adjustment.
- **Price/yield relationships:** price and yield move inversely; the higher the
  coupon the lower the sensitivity; the longer the maturity the higher the
  sensitivity.
- **Macaulay duration**, and from it **modified duration** = Macaulay / (1 + y/m).
- **Money duration** = modified duration x full price; **PVBP** (price value of a
  basis point) = money duration x 0.0001.
- **Price change approximation:** %change in price = -modified duration x change
  in yield + 0.5 x convexity x (change in yield)^2.
- **Effective duration** for embedded-option bonds (uses the benchmark curve, not
  the bond's own yield).
- **Convexity** definition and why positive convexity helps the holder.
- **Credit expected loss** = probability of default x loss given default.
- **Sources of return** from a bond: coupon income, reinvestment income, capital
  gain/loss.
- **Current yield, YTM, yield to call** definitions and when each is appropriate.

## Tier 2 — must understand

- Why a bond's holding period return equals its yield only when the horizon equals
  its Macaulay duration (a classic item).
- The difference between analytical and empirical duration.
- Key rate duration and what it measures that modified duration cannot.
- How credit enhancement structures (overcollateralisation, tranching, monoline
  guarantees) transfer risk.
- Prepayment risk: contraction and extension risk, and who bears which in a
  pass-through vs a CMO.
- Why callable bonds have negative convexity at low yields.

## Common traps

- **Semiannual by default** — the CFA curriculum's bond convention is semiannual
  payments unless the question says otherwise; compounding and period counts must
  match.
- Forgetting to **annualise** a yield computed per period.
- Using **modified duration with annual compounding when the convention is
  semiannual** — the (1 + y/m) divisor depends on frequency.
- Applying **duration alone for a large yield change** — the convexity adjustment
  is required, and the question will say "large".
- Confusing **money duration with PVBP** by a factor of 10000.
- Using **effective duration** for an option-free bond, or modified duration for
  one with embedded options.
- Reading **yield spread measures as equivalent** — they differ by convention.
- Mixing **probability of default with loss given default** in the expected-loss
  calculation.
- Forgetting that a **premium bond** has a capital loss to par by maturity, which
  is part of its total return.

## Typical question patterns

- Price a bond from a YTM, then from spot rates, and compare.
- Compute modified duration and PVBP, then the price change for a yield shift with
  and without the convexity adjustment.
- Given a price change, determine whether the bond has positive or negative
  convexity.
- Compute expected loss from PD and LGD.
- Forward rate from spot rates, and the arbitrage logic behind it.
- A comparison item on pass-throughs vs CMOs, or on credit enhancement methods.

## Free resources for this topic

- Official curriculum and topic questions: the Learning Ecosystem.
- Learning outcomes: the free 2027 Level I Topic Outlines PDF.
- Formula sheets for Fixed Income (free compilations).
- Calculator drilling on the bond worksheet (see `cfa.99.exam-preparation`).

## Practice target and revisits

- **200-260 questions** — the 19 modules mean you must cover breadth, so the
  question volume should be high even though many modules are light.
- Revisit the duration/convexity block before mocks 2 and 4; it decays fast.

## Dependencies

- Needs: discounting and TVM from Quantitative Methods; the risk machinery from
  Portfolio Construction.
- Feeds: nothing downstream, but it is the topic Equities valuation most resembles
  in method.

## Failure handling

- A bond question that does not state payment frequency -> assume semiannual, state
  the assumption, and keep it consistent throughout.
