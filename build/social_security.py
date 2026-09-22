"""Social Security benefits, following the rules described in the paper.

Anarkulova, Cederburg and O'Doherty (section 4.3) include US retirement
benefits and the SSI safety net. These incomes matter a lot for the probability
of ruin: a household whose financial capital runs out keeps receiving a
pension, so the paper's ruin measures the exhaustion of capital, not
destitution.

Rules used here, as stated in the text:

- 2022 progressive formula on average indexed monthly earnings (AIME), with
  bend points at 1,024 and 6,172 dollars per month and replacement rates of
  90%, 32% and 15%;
- annual cap of 147,000 dollars on the earnings counted in the AIME;
- claiming at 65, hence before full retirement age: the paper sets a reduction
  of 13.3% on the own benefit, 16.7% on the spousal benefit and 8.1% on the
  survivor benefit;
- spousal benefit equal to half the higher earner's benefit, used only if it
  exceeds the spouse's own benefit;
- SSI as a floor, at 1,261 dollars per month for a couple and 841 for a single
  person in 2022.

Full details are in the paper's Internet Appendix. This implementation uses
its published parameters, in an annual lifecycle engine that remains an
approximation of their monthly computation.
"""

from __future__ import annotations

# Bend points and replacement rates of the 2022 formula, in monthly dollars.
FIRST_BEND = 1_024.0
SECOND_BEND = 6_172.0
RATES = (0.90, 0.32, 0.15)
MAX_TAXABLE_EARNINGS = 147_000.0

# Reductions for claiming at 65, as set by the paper.
PERSONAL_PENALTY = 0.133
SPOUSAL_PENALTY = 0.167
SURVIVOR_PENALTY = 0.081

# Plancher SSI 2022, en dollars mensuels.
SSI_COUPLE = 1_261.0
SSI_SINGLE = 841.0

# Share of household income attributed to each spouse. The paper draws two
# separate careers; otherwise, a plausible unequal split is used that activates
# spousal benefits.
EARNINGS_SPLIT = (0.60, 0.40)


def primary_insurance_amount(monthly_earnings: float) -> float:
  """Monthly benefit at full retirement age, before the early-claiming reduction."""
  first = min(monthly_earnings, FIRST_BEND)
  second = max(0.0, min(monthly_earnings, SECOND_BEND) - FIRST_BEND)
  third = max(0.0, monthly_earnings - SECOND_BEND)
  return RATES[0] * first + RATES[1] * second + RATES[2] * third


def household_benefit(annual_income: float) -> tuple[float, float]:
  """Annual benefit of the couple, then of the survivor after a death.

  Both amounts are returned together because moving from one to the other
  changes household income without changing its capital: a couple that loses a
  spouse keeps the higher of the two benefits, not their sum.
  """
  earnings = max(0.0, annual_income)
  high = primary_insurance_amount(
    min(earnings * EARNINGS_SPLIT[0], MAX_TAXABLE_EARNINGS) / 12.0)
  low = primary_insurance_amount(
    min(earnings * EARNINGS_SPLIT[1], MAX_TAXABLE_EARNINGS) / 12.0)

  # Spousal benefit: half the higher earner's benefit, if it exceeds the
  # spouse's own benefit.
  spousal = max(low * (1.0 - PERSONAL_PENALTY),
                0.5 * high * (1.0 - SPOUSAL_PENALTY))
  primary = high * (1.0 - PERSONAL_PENALTY)

  couple_monthly = max(primary + spousal, SSI_COUPLE)
  # The survivor keeps the higher of the two benefits, reduced by the survivor
  # reduction.
  survivor_monthly = max(high * (1.0 - SURVIVOR_PENALTY), SSI_SINGLE)

  return couple_monthly * 12.0, survivor_monthly * 12.0


def average_indexed_monthly_earnings(
    annual_earnings: list[float], years: int = 35) -> float:
  """Approximate the AIME from a career in real dollars.

  The SSA first caps each annual income at the maximum taxable earnings, keeps
  the 35 highest years and fills a shorter career with zeros. Since the
  simulated incomes are already in 2022 dollars, we do not apply a second
  nominal wage indexation.
  """
  if years <= 0:
    raise ValueError("The number of AIME years must be strictly positive")
  best = sorted(
    (min(max(0.0, value), MAX_TAXABLE_EARNINGS)
     for value in annual_earnings),
    reverse=True,
  )
  best = (best + [0.0] * years)[:years]
  return sum(best) / (years * 12.0)


def household_benefit_from_histories(
    first_earnings: list[float],
    second_earnings: list[float],
    apply_ssi: bool = True,
    ) -> tuple[float, float]:
  """Annual benefit of the couple and of the survivor, career by career.

  This version is meant for the stochastic income model: it computes a
  separate AIME for each spouse, then applies the own, spousal and survivor
  benefits described in the paper.
  """
  pia = sorted((
    primary_insurance_amount(
      average_indexed_monthly_earnings(first_earnings)),
    primary_insurance_amount(
      average_indexed_monthly_earnings(second_earnings)),
  ), reverse=True)
  high, low = pia
  primary = high * (1.0 - PERSONAL_PENALTY)
  secondary = max(
    low * (1.0 - PERSONAL_PENALTY),
    0.5 * high * (1.0 - SPOUSAL_PENALTY),
  )
  couple_monthly = primary + secondary
  survivor_monthly = high * (1.0 - SURVIVOR_PENALTY)
  if apply_ssi:
    couple_monthly = max(couple_monthly, SSI_COUPLE)
    survivor_monthly = max(survivor_monthly, SSI_SINGLE)
  return couple_monthly * 12.0, survivor_monthly * 12.0


if __name__ == "__main__":
  print(f"{'annual income':>15}{'couple benefit':>17}{'survivor benefit':>19}"
        f"{'replacement rate':>19}")
  for income in (20_000, 31_500, 50_000, 80_000, 120_000):
    couple, survivor = household_benefit(income)
    print(f"{income:>15,.0f}{couple:>17,.0f}{survivor:>19,.0f}"
          f"{couple / income:>18.1%}".replace(",", " "))
