"""Construit la serie 'actions internationales' au sens d'Anarkulova, Cederburg
et O'Doherty (2023), reprise par Anarkulova-Cederburg-O'Doherty (2023, "Beyond
the Status Quo").

Definition du papier (section 3, p.369-370) : pour un pays donne, le rendement
international nominal est la moyenne ponderee par capitalisation boursiere des
rendements nominaux de TOUS les autres marches du panel, ajustee des variations
de change, puis converti en reel par l'inflation locale.

Le CSV contient aussi :

- un indice mondial incluant le marche du pays de residence, exprime dans la
  monnaie et le pouvoir d'achat de ce pays ;
- le taux de change du pays contre le dollar, necessaire pour convertir les
  autres poches mondiales dans le meme numeraire ;
- un contrefactuel
``international_equity_real_constant_real_fx`` : le meme panier, avec les memes
marches et les memes poids, mais en neutralisant la variation du taux de change
reel (change nominal plus ecart d'inflation). Figer le seul change nominal
creerait des rendements absurdes lors des hyperinflations etrangeres. Ce n'est
pas le rendement d'une couverture a terme (son carry et ses couts ne sont pas
modelises) ; cette serie sert uniquement a isoler le canal de change reel.

La ponderation canonique utilise la capitalisation historique de Kuvshinov et
Zimmermann, estimee comme le PIB comparable multiplie par leur ratio
capitalisation/PIB. Le PIB reel de Maddison ne sert de repli que pour les
annees dont la couverture en capitalisation est insuffisante. La conversion de
change utilise `xrusd`, le taux de change de chaque pays contre le dollar
fourni par JST, ce qui permet de passer d'un marche etranger a la devise
domestique via le dollar comme pivot.
"""

from __future__ import annotations

import argparse
import csv
import math
import os

# Le rendement d'un marche etranger et sa variation de change doivent rester
# couples : pendant l'hyperinflation allemande de 1923, le marche local gagne
# des milliards de pour cent nominaux et le mark en perd autant, les deux
# s'annulant presque. Neutraliser l'un sans l'autre produit des rendements
# absurdes.
#
# Le filtre porte donc sur le resultat converti, marche par marche : au-dela de
# ce seuil, la contribution du marche est ecartee et les poids sont
# renormalises sur les marches restants. Le papier signale des ajustements
# analogues autour des grandes ruptures (fermeture du NYSE en 1914, defaut grec
# de 2012).
# Des ruptures de prix ou de change restent dans le panel. Les supprimer sur
# la base du rendement realise utiliserait une information de fin de periode et
# modifierait retrospectivement le panier de l'investisseur. Les controles de
# qualite documentent les observations suspectes sans les filtrer ici.
MAX_CONVERTED_RETURN: float | None = None

# Les taux de change JST traversent la reforme Reichsmark--Deutsche Mark de
# 1948-49. Combiner ce saut de parite avec le rendement actions annuel de 1949
# reviendrait a attribuer a un investisseur etranger un rendement negociable
# continu au cours d'une fermeture et d'une conversion obligatoire. ACO (2025,
# Table A.III) documente la fermeture allemande jusqu'en 1948; notre frequence
# annuelle ne peut pas isoler proprement la reouverture de 1949. Cette
# exclusion est fondee sur la disponibilite du marche, jamais sur le rendement.
UNINVESTABLE_FOREIGN_MARKET_YEARS = {("Germany", 1949)}
MIN_CAP_COVERAGE = 0.75


GMD_NAMES = {"Australia": "Australia", "Belgium": "Belgium",
             "Denmark": "Denmark", "Finland": "Finland", "France": "France",
             "Germany": "Germany", "Italy": "Italy", "Japan": "Japan",
             "Netherlands": "Netherlands", "Norway": "Norway",
             "Portugal": "Portugal", "Spain": "Spain", "Sweden": "Sweden",
             "Switzerland": "Switzerland", "United Kingdom": "UK",
             "United States": "USA"}


def extend_recent(by_country: dict[str, dict[int, dict[str, float]]],
                  equity_path: str, gmd_path: str) -> None:
  """Prolonge le panel au-dela de JST avec les series 2021-2025.

  Les rendements actions viennent des indices de rendement total et des
  trackers cotes localement (``data/equity-tr-recent.csv``), l'inflation et les
  taux de change de la Global Macro Database (``data/gmd-cpi-fx.csv``).

  Les deux sources ne mesurent pas le change de la meme facon : JST publie un
  taux de fin d'annee, GMD une moyenne annuelle, avec des ecarts qui atteignent
  douze pour cent. Raccorder les niveaux fabriquerait donc un mouvement de
  change fictif en 2021. Seules les VARIATIONS de GMD sont reprises, appliquees
  au dernier taux JST connu.
  """
  if not (os.path.exists(equity_path) and os.path.exists(gmd_path)):
    return

  equity: dict[tuple[str, int], float] = {}
  with open(equity_path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      equity[(row["country"], int(row["year"]))] = float(row["equity_nominal"])

  macro: dict[tuple[str, int], dict[str, float]] = {}
  with open(gmd_path, encoding="utf-8", errors="ignore") as handle:
    for row in csv.DictReader(handle):
      country = GMD_NAMES.get(row["countryname"])
      if not country or not row["year"].isdigit():
        continue
      entry: dict[str, float] = {}
      for source, target in (("CPI", "cpi"), ("USDfx", "fx")):
        value = row.get(source, "").strip()
        if value not in ("", ".", "NA"):
          try:
            entry[target] = float(value)
          except ValueError:
            pass
      if len(entry) == 2:
        macro[(country, int(row["year"]))] = entry

  for country, years in by_country.items():
    pivot = max(years)
    anchor_fx = years[pivot]["xrusd"]
    anchor_cpi = years[pivot]["cpi"]
    for year in range(pivot + 1, pivot + 12):
      if (country, year) not in equity or (country, year) not in macro:
        break
      previous = macro.get((country, year - 1))
      current = macro[(country, year)]
      if not previous:
        break
      # Variation relative reprise de GMD, appliquee au niveau JST.
      anchor_fx *= current["fx"] / previous["fx"]
      anchor_cpi *= current["cpi"] / previous["cpi"]
      years[year] = {"eq_tr": equity[(country, year)],
                     "cpi": anchor_cpi, "xrusd": anchor_fx}


def read_jst(dta_path: str) -> dict[str, dict[int, dict[str, float]]]:
  import pandas as pd

  frame = pd.read_stata(dta_path)[
    ["year", "country", "eq_tr", "cpi", "xrusd"]].dropna()
  by_country: dict[str, dict[int, dict[str, float]]] = {}
  for record in frame.itertuples(index=False):
    by_country.setdefault(record.country, {})[int(record.year)] = {
      "eq_tr": record.eq_tr, "cpi": record.cpi, "xrusd": record.xrusd,
    }
  return by_country


def read_gdp_weights(dta_path: str) -> dict[tuple[str, int], float]:
  import pandas as pd

  frame = pd.read_stata(dta_path)[["year", "country", "rgdpmad", "pop"]]
  frame = frame.dropna(subset=["rgdpmad", "pop"])
  weights: dict[tuple[str, int], float] = {}
  for record in frame.itertuples(index=False):
    value = record.rgdpmad * record.pop
    if value > 0:
      weights[(record.country, int(record.year))] = value
  return weights


def extend_weights(weights: dict[tuple[str, int], float],
                   gmd_path: str) -> None:
  """Prolonge les poids de taille de marche au-dela de Maddison, via le PIB
  reel de la Global Macro Database, raccorde par pays sur la derniere annee
  commune."""
  if not os.path.exists(gmd_path):
    return

  recent: dict[tuple[str, int], float] = {}
  with open(gmd_path, encoding="utf-8", errors="ignore") as handle:
    for row in csv.DictReader(handle):
      country = GMD_NAMES.get(row["countryname"])
      if not country or not row["year"].isdigit():
        continue
      value = row.get("rGDP_USD", "").strip()
      if value in ("", ".", "NA"):
        continue
      try:
        number = float(value)
      except ValueError:
        continue
      if number > 0:
        recent[(country, int(row["year"]))] = number

  last = {}
  for country, year in weights:
    last[country] = max(last.get(country, 0), year)

  for country, pivot in last.items():
    if (country, pivot) not in recent:
      continue
    scale = weights[(country, pivot)] / recent[(country, pivot)]
    for (name, year), value in recent.items():
      if name == country and year > pivot:
          weights[(country, year)] = value * scale


def read_mcap_ratios(path: str) -> dict[tuple[str, int], float]:
  """Ratios capitalisation/PIB issus du fichier Big Bang mis en cache."""
  ratios: dict[tuple[str, int], float] = {}
  if not path or not os.path.exists(path):
    return ratios
  with open(path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      try:
        value = float(row["mcap_gdp"])
      except (KeyError, ValueError):
        continue
      if value > 0.0:
        ratios[(row["country"], int(row["year"]))] = value
  return ratios


def capitalization_weights(
    gdp_weights: dict[tuple[str, int], float],
    ratios: dict[tuple[str, int], float],
    ) -> dict[tuple[str, int], float]:
  return {
    key: gdp * ratios[key]
    for key, gdp in gdp_weights.items()
    if key in ratios and gdp > 0.0 and ratios[key] > 0.0
  }


def build(by_country: dict[str, dict[int, dict[str, float]]],
          gdp_weights: dict[tuple[str, int], float],
          cap_weights: dict[tuple[str, int], float],
          excluded_markets: frozenset[str] = frozenset(),
          excluded_market_years: frozenset[tuple[str, int]] = frozenset(),
          ) -> list[dict[str, float | str]]:
  """Pour chaque pays-annee, calcule le rendement reel des actions
  internationales telles que les verrait un investisseur de ce pays."""
  # Keep excluded countries as possible residents so that shared macro inputs
  # (notably U.S. CPI for the MF sleeve) remain available. They are removed
  # from every investable international/world basket below; callers that test
  # a source-country omission also remove their resident rows at simulation.
  countries = list(by_country)
  investable_countries = [country for country in countries
                          if country not in excluded_markets]
  rows: list[dict[str, float | str]] = []

  for domestic in countries:
    for year, entry in sorted(by_country[domestic].items()):
      # Les poids connus a la fin de l'annee precedente financent le rendement
      # de l'annee courante. Cela evite une ponderation qui connait deja la
      # performance mesuree. Une annee est entierement ponderee par
      # capitalisation ou entierement par PIB : les deux methodes ne sont
      # jamais melangees au sein d'un meme panier.
      weight_year = year - 1
      candidates = [c for c in investable_countries
                    if year in by_country[c] and year - 1 in by_country[c]]
      # Le panel de rendements commence parfois avant la premiere observation
      # de PIB de l'annee precedente. Pour cette seule bordure, conserver la
      # premiere annee avec les poids contemporains est preferable a supprimer
      # toute l'observation ; toutes les annees suivantes restent retardees.
      if sum((c, weight_year) in gdp_weights for c in candidates) < 5:
        weight_year = year
      cap_coverage = sum((c, weight_year) in cap_weights for c in candidates)
      if (candidates
          and cap_coverage / len(candidates) >= MIN_CAP_COVERAGE):
        weights = cap_weights
        weight_source = "capitalisation"
      else:
        weights = gdp_weights
        weight_source = "PIB proxy"

      others = [c for c in candidates
                if c != domestic and (c, weight_year) in weights]
      if len(others) < 4:
        continue

      shares_raw = [weights[(c, weight_year)] for c in others]
      total_weight = sum(shares_raw)
      if total_weight <= 0:
        continue
      shares = [w / total_weight for w in shares_raw]

      domestic_fx = by_country[domestic][year]["xrusd"]  # devise domestique / USD
      if not domestic_fx:
        continue

      # Rendement nominal de chaque marche etranger, converti en devise
      # domestique via le dollar comme pivot commun.
      nominal_international = 0.0
      real_international_constant_real_fx = 0.0
      retained_weight = 0.0
      for share, country in zip(shares, others):
        if ((country, year) in UNINVESTABLE_FOREIGN_MARKET_YEARS
            or (country, year) in excluded_market_years):
          continue
        foreign = by_country[country][year]
        foreign_fx = foreign["xrusd"]
        if not foreign_fx:
          continue
        # 1 unite de devise etrangere vaut (fx_domestique / fx_etranger) en
        # devise domestique. La variation de ce taux sur l'annee capture le
        # gain ou la perte de change ajoute au rendement local du marche.
        # Comme JST ne publie qu'un taux de fin de periode, l'annee precedente
        # sert de reference pour mesurer la variation.
        previous = by_country[domestic].get(year - 1, {})
        previous_foreign = by_country[country].get(year - 1, {})
        if not previous or not previous_foreign:
          continue
        foreign_inflation = foreign["cpi"] / previous_foreign["cpi"] - 1.0
        if foreign_inflation <= -1.0:
          continue
        fx_change = ((domestic_fx / foreign_fx)
                    / (previous["xrusd"] / previous_foreign["xrusd"])) - 1.0
        local_return = foreign["eq_tr"]
        # Rendement total pour l'investisseur domestique : le marche
        # etranger, compose avec la variation de change.
        converted = (1.0 + local_return) * (1.0 + fx_change) - 1.0
        if (not math.isfinite(converted)
            or (MAX_CONVERTED_RETURN is not None
                and abs(converted) > MAX_CONVERTED_RETURN)):
          continue
        nominal_international += share * converted
        # Meme marche, meme poids et meme filtre que dans le panier observe.
        # Le rendement reel local est ce que verrait l'investisseur si le taux
        # de change reel restait constant. Neutraliser seulement le change
        # nominal laisserait les hyperinflations etrangeres dans la serie.
        local_real_return = (
          (1.0 + local_return) / (1.0 + foreign_inflation) - 1.0
        )
        real_international_constant_real_fx += share * local_real_return
        retained_weight += share

      # Sans assez de marches exploitables, l'annee ne represente plus un
      # panier international.
      if retained_weight < 0.5:
        continue
      nominal_international /= retained_weight
      real_international_constant_real_fx /= retained_weight

      inflation_previous = by_country[domestic].get(year - 1, {}).get("cpi")
      inflation_current = entry["cpi"]
      if not inflation_previous:
        continue
      inflation = inflation_current / inflation_previous - 1.0
      if inflation <= -1.0:
        continue

      real_international = (1.0 + nominal_international) / (1.0 + inflation) - 1.0

      # Indice mondial vu par le meme resident. Contrairement a l'ancienne
      # serie commune en dollars reels, chaque marche est d'abord converti
      # dans la monnaie du pays de residence puis deflate par son inflation.
      # Toutes les poches d'une ligne pays-annee partagent ainsi le meme
      # numeraire. Le marche domestique est inclus dans cet agregat.
      world_candidates = [
        c for c in candidates if (c, weight_year) in weights
      ]
      world_raw = [weights[(c, weight_year)] for c in world_candidates]
      world_total = sum(world_raw)
      if world_total <= 0.0:
        continue
      world_shares = [value / world_total for value in world_raw]
      nominal_world = 0.0
      retained_world_weight = 0.0
      retained_world_markets = 0
      previous_domestic = by_country[domestic].get(year - 1, {})
      if not previous_domestic:
        continue
      for share, country in zip(world_shares, world_candidates):
        if ((country, year) in UNINVESTABLE_FOREIGN_MARKET_YEARS
            or (country, year) in excluded_market_years):
          continue
        market = by_country[country][year]
        previous_market = by_country[country].get(year - 1, {})
        if not previous_market or not market["xrusd"]:
          continue
        fx_change = ((domestic_fx / market["xrusd"])
                    / (previous_domestic["xrusd"]
                       / previous_market["xrusd"])) - 1.0
        converted = (1.0 + market["eq_tr"]) * (1.0 + fx_change) - 1.0
        if (not math.isfinite(converted)
            or (MAX_CONVERTED_RETURN is not None
                and abs(converted) > MAX_CONVERTED_RETURN)):
          continue
        nominal_world += share * converted
        retained_world_weight += share
        retained_world_markets += 1
      if retained_world_weight < 0.5:
        continue
      nominal_world /= retained_world_weight
      real_world = (1.0 + nominal_world) / (1.0 + inflation) - 1.0

      rows.append({
        "country": domestic, "year": year,
        "international_equity_real": real_international,
        "international_equity_real_constant_real_fx":
          real_international_constant_real_fx,
        "world_equity_real_resident": real_world,
        "resident_xrusd": domestic_fx,
        "markets": len(others),
        "world_markets": retained_world_markets,
        "weight_source": weight_source,
      })

  return rows


def main() -> None:
  here = os.path.dirname(os.path.abspath(__file__))
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--dta", default=os.path.join(
    here, "..", "data", "JSTdatasetR6.dta"))
  parser.add_argument("--equity", default=os.path.join(
    here, "..", "data", "equity-tr-recent.csv"))
  parser.add_argument("--gmd", default=os.path.join(
    here, "..", "data", "gmd-cpi-fx.csv"))
  parser.add_argument("--mcap", default=os.path.join(
    here, "..", "data", "bb-mcap-gdp.csv"))
  parser.add_argument("--out", default=os.path.join(
    here, "..", "data", "international-equity.csv"))
  parser.add_argument("--max-converted-return", type=float,
                      help="legacy diagnostic only: drop a foreign constituent when its absolute converted nominal return exceeds this value")
  parser.add_argument("--exclude-market", action="append", default=[],
                      help="remove a country from every international and world basket (repeatable)")
  parser.add_argument("--exclude-market-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a source country-year from every equity basket")
  args = parser.parse_args()

  by_country = read_jst(args.dta)
  extend_recent(by_country, args.equity, args.gmd)
  gdp_weights = read_gdp_weights(args.dta)
  extend_weights(gdp_weights, args.gmd)
  ratios = read_mcap_ratios(args.mcap)
  cap_weights = capitalization_weights(gdp_weights, ratios)
  global MAX_CONVERTED_RETURN
  MAX_CONVERTED_RETURN = args.max_converted_return
  unknown = sorted(set(args.exclude_market) - set(by_country))
  if unknown:
    raise ValueError(f"unknown market(s): {', '.join(unknown)}")
  excluded_market_years = set()
  for value in args.exclude_market_year:
    try:
      country, year = value.rsplit(":", 1)
      excluded_market_years.add((country, int(year)))
    except ValueError as error:
      raise ValueError("--exclude-market-year must be COUNTRY:YEAR") from error
  rows = build(by_country, gdp_weights, cap_weights,
               frozenset(args.exclude_market), frozenset(excluded_market_years))

  print(f"{len(rows)} observations, {len({r['country'] for r in rows})} pays")
  print(f"marches moyens par observation : "
       f"{sum(r['markets'] for r in rows) / len(rows):.1f}")
  sources: dict[str, int] = {}
  for row in rows:
    source = str(row["weight_source"])
    sources[source] = sources.get(source, 0) + 1
  print("ponderations : " + ", ".join(
    f"{source}={count}" for source, count in sorted(sources.items())))

  with open(args.out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=[
      "country", "year", "international_equity_real",
      "international_equity_real_constant_real_fx",
      "world_equity_real_resident", "resident_xrusd", "markets",
      "world_markets", "weight_source"])
    writer.writeheader()
    writer.writerows(rows)
  print(f"Ecrit dans {os.path.normpath(args.out)}")


if __name__ == "__main__":
  main()
