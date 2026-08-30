"""Prestations de Social Security, selon les regles decrites par le papier.

Anarkulova, Cederburg et O'Doherty (section 4.3) incorporent les prestations
de retraite americaines et le filet de securite du SSI. Ces revenus comptent
beaucoup pour la probabilite de ruine : un menage dont le capital financier
s'epuise continue de percevoir une pension, si bien que la ruine du papier
mesure l'epuisement du capital et non la misere.

Regles reprises ici, telles que le texte les enonce :

- formule progressive de 2022 sur le revenu moyen indexe (AIME), avec les
  points d'inflexion a 1 024 et 6 172 dollars mensuels et les taux de
  remplacement de 90 %, 32 % et 15 % ;
- plafond annuel de 147 000 dollars sur les revenus retenus dans l'AIME ;
- depart a 65 ans, donc avant l'age du taux plein : le papier chiffre une
  penalite de 13,3 % sur la pension personnelle, 16,7 % sur la pension de
  conjoint et 8,1 % sur la reversion ;
- prestation de conjoint egale a la moitie de la pension du conjoint mieux
  remunere, retenue seulement si elle depasse la pension propre ;
- SSI comme plancher, a 1 261 dollars par mois pour un couple et 841 pour une
  personne seule en 2022.

Le detail complet figure dans l'Internet Appendix du papier. Cette
implementation en reprend les parametres publies, dans un moteur de cycle de
vie annuel qui reste une approximation de leur calcul mensuel.
"""

from __future__ import annotations

# Points d'inflexion et taux de remplacement de la formule 2022, en dollars
# mensuels.
FIRST_BEND = 1_024.0
SECOND_BEND = 6_172.0
RATES = (0.90, 0.32, 0.15)
MAX_TAXABLE_EARNINGS = 147_000.0

# Penalites de depart a 65 ans, chiffrees par le papier.
PERSONAL_PENALTY = 0.133
SPOUSAL_PENALTY = 0.167
SURVIVOR_PENALTY = 0.081

# Plancher SSI 2022, en dollars mensuels.
SSI_COUPLE = 1_261.0
SSI_SINGLE = 841.0

# Part du revenu du menage attribuee a chaque conjoint. Le papier tire deux
# carrieres distinctes ; a defaut, on retient un partage inegal plausible qui
# active les prestations de conjoint.
EARNINGS_SPLIT = (0.60, 0.40)


def primary_insurance_amount(monthly_earnings: float) -> float:
  """Pension mensuelle au taux plein, avant penalite de depart anticipe."""
  first = min(monthly_earnings, FIRST_BEND)
  second = max(0.0, min(monthly_earnings, SECOND_BEND) - FIRST_BEND)
  third = max(0.0, monthly_earnings - SECOND_BEND)
  return RATES[0] * first + RATES[1] * second + RATES[2] * third


def household_benefit(annual_income: float) -> tuple[float, float]:
  """Pension annuelle du couple, puis celle du survivant apres un deces.

  Les deux montants sont renvoyes ensemble parce que le passage de l'un a
  l'autre change le revenu du menage sans changer son capital : un couple qui
  perd un conjoint garde la meilleure des deux pensions, pas leur somme.
  """
  earnings = max(0.0, annual_income)
  high = primary_insurance_amount(
    min(earnings * EARNINGS_SPLIT[0], MAX_TAXABLE_EARNINGS) / 12.0)
  low = primary_insurance_amount(
    min(earnings * EARNINGS_SPLIT[1], MAX_TAXABLE_EARNINGS) / 12.0)

  # Prestation de conjoint : la moitie de la pension du mieux remunere, si
  # elle depasse la pension propre du conjoint.
  spousal = max(low * (1.0 - PERSONAL_PENALTY),
                0.5 * high * (1.0 - SPOUSAL_PENALTY))
  primary = high * (1.0 - PERSONAL_PENALTY)

  couple_monthly = max(primary + spousal, SSI_COUPLE)
  # Le survivant conserve la meilleure des deux pensions, diminuee de la
  # penalite de reversion.
  survivor_monthly = max(high * (1.0 - SURVIVOR_PENALTY), SSI_SINGLE)

  return couple_monthly * 12.0, survivor_monthly * 12.0


def average_indexed_monthly_earnings(
    annual_earnings: list[float], years: int = 35) -> float:
  """Approximation de l'AIME a partir d'une carriere en dollars reels.

  La SSA plafonne d'abord chaque revenu annuel aux revenus taxables maximaux,
  retient les 35 meilleures annees et complete une carriere plus courte par
  des zeros. Les revenus simules etant deja exprimes en dollars 2022, nous
  n'appliquons pas une seconde indexation salariale nominale.
  """
  if years <= 0:
    raise ValueError("Le nombre d'annees AIME doit etre strictement positif")
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
  """Pension annuelle du couple et du survivant, carriere par carriere.

  Cette version est destinee au modele de revenus stochastiques : elle calcule
  une AIME distincte pour chaque conjoint, puis applique les prestations
  personnelles, de conjoint et de survivant decrites dans le papier.
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
  print(f"{'revenu annuel':>15}{'pension couple':>17}{'pension survivant':>19}"
        f"{'taux remplacement':>19}")
  for income in (20_000, 31_500, 50_000, 80_000, 120_000):
    couple, survivor = household_benefit(income)
    print(f"{income:>15,.0f}{couple:>17,.0f}{survivor:>19,.0f}"
          f"{couple / income:>18.1%}".replace(",", " "))
