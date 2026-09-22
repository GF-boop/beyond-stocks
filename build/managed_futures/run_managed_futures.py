"""Reproduit un proxy managed futures mensuel 1/6/12 mois.

Le script lit uniquement le snapshot canonique local. Il ne telecharge rien et
ne reconstruit aucune donnee de marche. Par defaut, les signaux du mois t sont
arretes au mois t-2 : le mois t-1 est saute afin de neutraliser le chevauchement
des prix sources qui sont souvent des moyennes mensuelles.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE.parents[1] / "data" / "mf-inputs" / "all-assets-monthly.csv"
DEFAULT_COLLATERAL = HERE.parents[1] / "data" / "mf-inputs" / "cash-returns-monthly.csv"
DEFAULT_FX_SPOT = HERE.parents[1] / "data" / "mf-inputs" / "fx-spot-returns-monthly.csv"
DEFAULT_OUTPUT = HERE / "output"

HORIZONS = (1, 3, 6, 12)
VOL_WINDOW = 36
MIN_VOL_OBSERVATIONS = 24
ASSET_VOL_TARGET = 0.15
PORTFOLIO_VOL_TARGET = 0.10
MAX_ASSET_LEVERAGE = 4.0
MAX_PORTFOLIO_SCALAR = 3.0
MIN_ACTIVE_SECTORS = 2
SECTOR_WEIGHTINGS = ("equal", "inverse_vol")

VARIANTS = {
    "signal_1m": (1,),
    "signal_3m": (3,),
    "signal_6m": (6,),
    "signal_12m": (12,),
    # Combinaison publiee par Hurst, Ooi et Pedersen (2017).
    "mf_1_3_12": (1, 3, 12),
    # Variante de recherche propre a ce projet.
    "mf_1_6_12": (1, 6, 12),
}

UNIVERSE_PROFILES = {
    # KMLM est construit sur commodities, devises et obligations globales;
    # cette composition est aussi la plus fidele aux instruments availables
    # localement, contrairement aux 18 indices actions cash nationaux.
    "futures_core": {"bond", "commodity", "currency"},
    # Reproduction exacte du proxy historique, conservee pour sensibilite.
    "legacy_three_sector": {"equity", "bond", "commodity"},
    # Version SG-like : quatre secteurs, mais actions cash toujours imparfaites.
    "all_four_sectors": {"equity", "bond", "commodity", "currency"},
    # Avant les devises convertibles, les actions nationales apportent le
    # troisieme secteur disponible. Elles sont retirees lorsque les cinq
    # devises H.10 deviennent disponibles, afin de ne pas degrader l'univers
    # CTA moderne par des indices actions cash.
    "historical_equity_transition": {"equity", "bond", "commodity", "currency"},
}

EQUITY_TRANSITION_END = "1970-12"

# Les rendements locaux ne sont convertis en USD que lorsque le spot USD de
# leur devise est effectivement disponible dans le snapshot. Les pays de la
# zone euro n'emploient donc EUR qu'a partir de 1999; avant, leurs P&L locaux
# sont exclus plutot que traites implicitement comme des P&L USD.
COUNTRY_FX_ASSET = {
    "AUS": "FX_AUD", "CAN": "FX_CAD", "CHE": "FX_CHF",
    "GBR": "FX_GBP", "JPN": "FX_JPY",
    "BEL": "FX_EUR", "DEU": "FX_EUR", "ESP": "FX_EUR",
    "FIN": "FX_EUR", "FRA": "FX_EUR", "IRL": "FX_EUR",
    "ITA": "FX_EUR", "NLD": "FX_EUR", "PRT": "FX_EUR",
}


@dataclass(frozen=True)
class Market:
  asset_id: str
  sector: str
  returns: dict[str, float]
  signal_skip_months: int
  return_kind: str


def month_number(month: str) -> int:
  year, number = map(int, month.split("-"))
  return year * 12 + number - 1


def load_markets(path: Path) -> tuple[list[str], dict[str, Market]]:
  raw: dict[str, dict[str, float]] = defaultdict(dict)
  classes: dict[str, str] = {}
  return_kinds: dict[str, str] = {}
  with path.open(newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      if row["default_universe"] != "yes":
        continue
      asset_class = row["asset_class"]
      if asset_class not in {"equity", "bond", "commodity", "precious_metal", "currency"}:
        continue
      asset = row["asset_id"]
      raw[asset][row["month"]] = float(row["return"])
      # Or et argent appartiennent au secteur commodities pour ne pas creer un
      # pseudo-secteur de deux marches surpondere a un tiers du CTA.
      classes[asset] = "commodity" if asset_class == "precious_metal" else asset_class
      return_kinds[asset] = row["return_kind"]

  markets = {
      asset: Market(
          asset, classes[asset], values,
          # Les prix mensuels moyens ne peuvent pas utiliser t-1 sans
          # chevauchement. Les devises H.10 sont au contraire des closings EOM.
          0 if return_kinds[asset] in {
              "spot_eom_price_return", "forward_excess_return",
          } else 1,
          return_kinds[asset],
      )
      for asset, values in raw.items()
  }
  months = sorted({month for market in markets.values() for month in market.returns})
  if not markets or not months:
    raise ValueError("snapshot canonique vide")
  return months, markets


def load_fx_spot_returns(path: Path) -> dict[str, dict[str, float]]:
  """Lit les variations spot USD, distinctes des rendements de forwards FX."""
  values: dict[str, dict[str, float]] = defaultdict(dict)
  with path.open(newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      month = row["month"]
      for asset, value in row.items():
        if asset != "month" and value:
          values[asset][month] = float(value)
  if not values:
    raise ValueError(f"fichier spot FX vide: {path}")
  return dict(values)


def market_country(asset_id: str) -> str | None:
  if asset_id.startswith("EQ_"):
    return asset_id.removeprefix("EQ_")
  if asset_id.startswith("BOND_") and asset_id.endswith("_10Y"):
    return asset_id.removeprefix("BOND_").removesuffix("_10Y")
  return None


def normalize_local_pnl_to_usd(
    markets: dict[str, Market], fx_spot: dict[str, dict[str, float]],
    futures_pnl_fx: bool,
) -> dict[str, Market]:
  """Convertit les retours locaux en USD au spot EOM.

  Les actions portent un principal FX. Les obligations sont des P&L
  synthetiques en exces de cash: sous ``futures_pnl_fx``, seul ce P&L est
  converti, afin qu'un P&L local nul reste nul comme pour un futures collatéral.
  """
  normalized: dict[str, Market] = {}
  for asset, market in markets.items():
    country = market_country(asset)
    if country is None or country == "USA":
      normalized[asset] = market
      continue
    fx_asset = COUNTRY_FX_ASSET.get(country)
    if fx_asset is None:
      continue
    spot = fx_spot.get(fx_asset, {})
    converted = {
        month: (local_return * (1.0 + spot[month])
                if futures_pnl_fx and market.return_kind == "synthetic_excess_return"
                else (1.0 + local_return) * (1.0 + spot[month]) - 1.0)
        for month, local_return in market.returns.items()
        if month in spot
    }
    if converted:
      normalized[asset] = Market(
          market.asset_id, market.sector, converted, market.signal_skip_months,
          market.return_kind,
      )
  if not normalized:
    raise ValueError("normalisation USD: aucun marche exploitable")
  return normalized


def select_universe(markets: dict[str, Market], profile: str) -> dict[str, Market]:
  sectors = UNIVERSE_PROFILES[profile]
  selected: dict[str, Market] = {}
  for asset, market in markets.items():
    if market.sector not in sectors:
      continue
    values = market.returns
    if profile == "historical_equity_transition" and market.sector == "equity":
      values = {month: value for month, value in values.items()
                if month <= EQUITY_TRANSITION_END}
    if values:
      selected[asset] = Market(
          market.asset_id, market.sector, values, market.signal_skip_months,
          market.return_kind,
      )
  if not selected:
    raise ValueError(f"univers {profile} vide")
  return selected


def load_usd_collateral(path: Path) -> dict[str, float]:
  """Lit le rendement cash USD deja decale d'un mois dans le snapshot."""
  with path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    if "USA" not in (reader.fieldnames or []):
      raise ValueError(f"colonne USA absente du collateral: {path}")
    return {
        row["month"]: float(row["USA"])
        for row in reader if row.get("USA")
    }


def previous_calendar_months(months: list[str], position: int, length: int) -> list[str]:
  if position < length:
    return []
  window = months[position - length:position]
  if not window:
    return []
  expected_start = month_number(months[position]) - length
  if month_number(window[0]) != expected_start:
    return []
  return window


def momentum_signal(
    values: dict[str, float], history: list[str], horizon: int,
) -> float | None:
  window = history[-horizon:]
  if len(window) != horizon or not all(month in values for month in window):
    return None
  momentum = sum(math.log1p(values[month]) for month in window)
  if abs(momentum) < 1e-15:
    return 0.0
  return 1.0 if momentum > 0 else -1.0


def lagged_volatility(values: dict[str, float], history: list[str]) -> float | None:
  observations = [values[month] for month in history if month in values]
  if len(observations) < MIN_VOL_OBSERVATIONS:
    return None
  volatility = statistics.stdev(observations) * math.sqrt(12)
  return volatility if volatility > 1e-12 else None


def sector_allocation(
    sectors: dict[str, float], historical_sectors: dict[str, dict[str, float]],
    history: list[str], method: str,
) -> dict[str, float]:
  """Alloue les secteurs avec les seules informations disponibles avant t.

  ``inverse_vol`` est une risk-parity diagonale volontairement robuste : il ne
  tente pas d'inverser une matrice de covariance instable quand l'univers
  historique s'elargit. Tant que tous les secteurs actifs n'ont pas 24 mois
  d'observations, il retombe explicitement sur l'equiponderation.
  """
  if method == "equal":
    return {sector: 1.0 / len(sectors) for sector in sectors}
  if method != "inverse_vol":
    raise ValueError(f"ponderation sectorielle inconnue: {method}")
  volatilities: dict[str, float] = {}
  for sector in sectors:
    observations = [historical_sectors.get(month, {}).get(sector)
                    for month in history]
    observed = [value for value in observations if value is not None]
    if len(observed) < MIN_VOL_OBSERVATIONS:
      return {item: 1.0 / len(sectors) for item in sectors}
    volatility = statistics.stdev(observed) * math.sqrt(12)
    if volatility <= 1e-12:
      return {item: 1.0 / len(sectors) for item in sectors}
    volatilities[sector] = volatility
  inverse = {sector: 1.0 / volatility for sector, volatility in volatilities.items()}
  total = sum(inverse.values())
  return {sector: value / total for sector, value in inverse.items()}


def build_raw_variants(
    months: list[str], markets: dict[str, Market], signal_skip_months: int,
    sector_weighting: str = "equal",
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, dict[str, dict[str, float]]],
    dict[str, dict[str, dict[str, float]]],
    dict[str, dict[str, float]],
    dict[str, dict[str, int]],
    list[dict[str, str]],
]:
  raw_returns = {variant: {} for variant in VARIANTS}
  raw_weights = {variant: {} for variant in VARIANTS}
  sector_returns = {variant: {} for variant in VARIANTS}
  combined_signals: dict[str, dict[str, float]] = {}
  active_counts: dict[str, dict[str, int]] = {}
  position_audit: list[dict[str, str]] = []

  for index, month in enumerate(months):
    volatility_history = previous_calendar_months(months, index, VOL_WINDOW)
    if len(volatility_history) != VOL_WINDOW:
      continue

    # Information retardee, commune aux quatre variantes.
    market_state: dict[str, dict[str, float]] = {}
    for asset, market in markets.items():
      if month not in market.returns:
        continue
      effective_skip = 0 if market.signal_skip_months == 0 else signal_skip_months
      signal_position = index - effective_skip
      signal_history = previous_calendar_months(
          months, signal_position, VOL_WINDOW,
      ) if signal_position >= 0 else []
      if len(signal_history) != VOL_WINDOW:
        continue
      volatility = lagged_volatility(market.returns, volatility_history)
      if volatility is None:
        continue
      signals = {
          horizon: momentum_signal(market.returns, signal_history, horizon)
          for horizon in HORIZONS
      }
      leverage = min(ASSET_VOL_TARGET / volatility, MAX_ASSET_LEVERAGE)
      market_state[asset] = {
          "volatility": volatility,
          "leverage": leverage,
          **{f"signal_{horizon}": signals[horizon]
             for horizon in HORIZONS},
      }

    for variant, horizons in VARIANTS.items():
      candidates: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
      signals_for_variant: dict[str, float] = {}
      for asset, state in market_state.items():
        individual = [state[f"signal_{horizon}"] for horizon in horizons]
        if any(signal is None for signal in individual):
          continue
        signal = statistics.fmean(float(value) for value in individual)
        signals_for_variant[asset] = signal
        market = markets[asset]
        contribution = signal * state["leverage"] * market.returns[month]
        candidates[market.sector].append((asset, contribution, state["leverage"] * signal))

      if len(candidates) < MIN_ACTIVE_SECTORS:
        continue
      sectors: dict[str, float] = {}
      for sector, members in candidates.items():
        sectors[sector] = statistics.fmean(item[1] for item in members)
      historical_sectors = sector_returns[variant]
      allocations = sector_allocation(
          sectors, historical_sectors, volatility_history, sector_weighting,
      )
      weights: dict[str, float] = {}
      for sector, members in candidates.items():
        for asset, _contribution, exposure in members:
          weights[asset] = exposure / len(members) * allocations[sector]
      raw_returns[variant][month] = sum(
          allocations[sector] * value for sector, value in sectors.items()
      )
      raw_weights[variant][month] = weights
      sector_returns[variant][month] = sectors

      if variant == "mf_1_6_12":
        combined_signals[month] = signals_for_variant
        active_counts[month] = {
            "equity": len(candidates.get("equity", [])),
            "bond": len(candidates.get("bond", [])),
            "commodity": len(candidates.get("commodity", [])),
            "currency": len(candidates.get("currency", [])),
            "sectors": len(candidates),
        }
        for asset, signal in sorted(signals_for_variant.items()):
          state = market_state[asset]
          if asset not in weights:
            continue
          position_audit.append({
              "month": month,
              "asset_id": asset,
              "sector": markets[asset].sector,
              "signal_1m": f"{state['signal_1']:.12g}",
              "signal_3m": f"{state['signal_3']:.12g}",
              "signal_6m": f"{state['signal_6']:.12g}",
              "signal_12m": f"{state['signal_12']:.12g}",
              "combined_signal": f"{signal:.12g}",
              "annualized_vol": f"{state['volatility']:.12g}",
              "asset_leverage": f"{state['leverage']:.12g}",
              "sector_weight": f"{allocations[markets[asset].sector]:.12g}",
              "raw_portfolio_weight": f"{weights[asset]:.12g}",
          })

  return (raw_returns, raw_weights, sector_returns, combined_signals,
          active_counts, position_audit)


def target_and_cost(
    months: list[str],
    raw_returns: dict[str, float],
    raw_weights: dict[str, dict[str, float]],
    usd_collateral: dict[str, float],
    add_usd_collateral: bool,
    annual_fee: float,
    transaction_bps: float,
) -> dict[str, dict[str, float]]:
  result: dict[str, dict[str, float]] = {}
  previous_weights: dict[str, float] = {}
  monthly_fee = (1.0 + annual_fee) ** (1.0 / 12.0) - 1.0

  for index, month in enumerate(months):
    if month not in raw_returns:
      continue
    history_months = previous_calendar_months(months, index, VOL_WINDOW)
    history = [raw_returns[item] for item in history_months if item in raw_returns]
    if len(history) < MIN_VOL_OBSERVATIONS:
      continue
    raw_volatility = statistics.stdev(history) * math.sqrt(12)
    if raw_volatility <= 1e-12:
      continue
    scalar = min(PORTFOLIO_VOL_TARGET / raw_volatility, MAX_PORTFOLIO_SCALAR)
    weights = {asset: scalar * value
               for asset, value in raw_weights[month].items()}
    all_assets = set(previous_weights) | set(weights)
    turnover = sum(abs(weights.get(asset, 0.0) - previous_weights.get(asset, 0.0))
                   for asset in all_assets)
    transaction_cost = turnover * transaction_bps / 10_000.0
    excess_pnl = scalar * raw_returns[month]
    collateral = usd_collateral.get(month, 0.0) if add_usd_collateral else 0.0
    # Le P&L des contrats (obligations/FX en exces de cash, commodities a
    # roll nul) est reinvesti avec le collateral USD du NAV.
    gross = (1.0 + collateral) * (1.0 + excess_pnl) - 1.0
    net = gross - transaction_cost - monthly_fee
    result[month] = {
        "raw_return": raw_returns[month],
        "cash_collateral_return": collateral,
        "gross_return": gross,
        "net_return": net,
        "portfolio_vol_scalar": scalar,
        "gross_exposure": sum(abs(value) for value in weights.values()),
        "turnover": turnover,
        "transaction_cost": transaction_cost,
        "management_fee": monthly_fee,
        "ex_ante_raw_vol": raw_volatility,
    }
    previous_weights = weights
  return result


def max_drawdown(values: list[float]) -> float:
  wealth = 1.0
  peak = 1.0
  drawdown = 0.0
  for value in values:
    wealth *= 1.0 + value
    peak = max(peak, wealth)
    drawdown = min(drawdown, wealth / peak - 1.0)
  return drawdown


def summary_row(
    variant: str, kind: str, period: str,
    selected: list[tuple[str, float]],
) -> dict[str, str | int]:
  values = [value for _month, value in selected]
  growth = math.prod(1.0 + value for value in values)
  annualized_return = growth ** (12.0 / len(values)) - 1.0
  volatility = statistics.stdev(values) * math.sqrt(12)
  arithmetic = statistics.fmean(values) * 12
  return {
      "variant": variant,
      "return_kind": kind,
      "period": period,
      "first_month": selected[0][0],
      "last_month": selected[-1][0],
      "months": len(values),
      "cagr": f"{annualized_return:.12g}",
      "annualized_mean": f"{arithmetic:.12g}",
      "annualized_vol": f"{volatility:.12g}",
      "sharpe_zero_cash": f"{arithmetic / volatility:.12g}",
      "max_drawdown": f"{max_drawdown(values):.12g}",
      "positive_months": f"{sum(value > 0 for value in values) / len(values):.12g}",
  }


def build_summaries(targeted: dict[str, dict[str, dict[str, float]]]) -> list[dict]:
  rows: list[dict] = []
  periods = (
      ("full", "0000-00"),
      ("1960-2025", "1960-01"),
      ("1980-2025", "1980-01"),
      ("2000-2025", "2000-01"),
      ("2010-2025", "2010-01"),
  )
  for variant, observations in targeted.items():
    for kind, field in (("gross", "gross_return"), ("net", "net_return")):
      for label, start in periods:
        selected = [(month, values[field]) for month, values in sorted(observations.items())
                    if month >= start]
        if len(selected) >= 24:
          rows.append(summary_row(variant, kind, label, selected))
  return rows


def write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
  with path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def build_annual_rows(
    targeted: dict[str, dict[str, dict[str, float]]],
) -> tuple[list[dict[str, str]], list[str]]:
  """Compose les douze mois; les annees calendaires partielles sont exclues."""
  fields = ["year"]
  for variant in VARIANTS:
    fields.extend((f"{variant}_gross_return", f"{variant}_net_return"))
  rows: list[dict[str, str]] = []
  years = sorted({int(month[:4]) for values in targeted.values()
                  for month in values})
  for year in years:
    calendar = [f"{year:04d}-{month:02d}" for month in range(1, 13)]
    if not all(all(month in targeted[variant] for month in calendar)
               for variant in VARIANTS):
      continue
    row = {"year": str(year)}
    for variant in VARIANTS:
      for kind in ("gross", "net"):
        field = f"{kind}_return"
        annual = math.prod(
            1.0 + targeted[variant][month][field] for month in calendar
        ) - 1.0
        row[f"{variant}_{field}"] = f"{annual:.12g}"
    rows.append(row)
  return rows, fields


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
  parser.add_argument("--collateral-input", type=Path, default=DEFAULT_COLLATERAL)
  parser.add_argument("--fx-spot-input", type=Path, default=DEFAULT_FX_SPOT)
  parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
  parser.add_argument("--annual-fee", type=float, default=0.0085)
  parser.add_argument("--transaction-bps", type=float, default=3.0)
  parser.add_argument(
      "--add-usd-collateral", action=argparse.BooleanOptionalAction, default=True,
      help="ajoute le rendement cash USD du NAV aux P&L futures (defaut: oui)",
  )
  parser.add_argument(
      "--normalize-local-pnl-to-usd", action=argparse.BooleanOptionalAction,
      default=True,
      help=("convertit actions et obligations locales au spot USD; les marches "
            "sans spot sont exclus (defaut: oui)"),
  )
  parser.add_argument(
      "--futures-pnl-fx", action=argparse.BooleanOptionalAction, default=True,
      help=("convertit les P&L obligataires synthetiques en exces de cash sans "
            "exposer leur principal au change; convention centrale, defaut: oui"),
  )
  parser.add_argument(
      "--universe-profile", choices=sorted(UNIVERSE_PROFILES),
      default="all_four_sectors",
      help=("univers de marche; all_four_sectors (actions, obligations, "
            "commodities, devises) est le profil canonique : il conserve "
            "quatre secteurs sur tout l'echantillon, la ou futures_core "
            "tombe a deux secteurs avant 1971"),
  )
  parser.add_argument(
      "--sector-weighting", choices=SECTOR_WEIGHTINGS, default="inverse_vol",
      help=("ponderation des secteurs : equal, ou inverse_vol pour une "
            "risk-parity sectorielle retardee"),
  )
  parser.add_argument(
      "--signal-skip-months", type=int, default=1,
      help=("mois complets sautes entre la fin du signal et le mois investi; "
            "1 par defaut pour les prix sources en moyenne mensuelle"),
  )
  args = parser.parse_args()
  if args.signal_skip_months < 0:
    parser.error("--signal-skip-months doit etre positif ou nul")
  args.output.mkdir(parents=True, exist_ok=True)

  months, all_markets = load_markets(args.input)
  if args.normalize_local_pnl_to_usd:
    all_markets = normalize_local_pnl_to_usd(
        all_markets, load_fx_spot_returns(args.fx_spot_input), args.futures_pnl_fx,
    )
    months = sorted({month for market in all_markets.values()
                     for month in market.returns})
  usd_collateral = load_usd_collateral(args.collateral_input)
  markets = select_universe(all_markets, args.universe_profile)
  (raw, weights, sectors, _signals, active_counts,
   position_audit) = build_raw_variants(
       months, markets, args.signal_skip_months, args.sector_weighting,
   )
  targeted = {
      variant: target_and_cost(
          months, raw[variant], weights[variant],
          usd_collateral, args.add_usd_collateral,
          args.annual_fee, args.transaction_bps,
      )
      for variant in VARIANTS
  }

  main_rows: list[dict[str, str]] = []
  common_months = sorted({month for values in targeted.values() for month in values})
  for month in common_months:
    row: dict[str, str] = {"month": month}
    for variant in VARIANTS:
      values = targeted[variant].get(month)
      for field in ("gross_return", "net_return", "cash_collateral_return", "portfolio_vol_scalar",
                    "gross_exposure", "turnover", "transaction_cost"):
        row[f"{variant}_{field}"] = (
            f"{values[field]:.12g}" if values else ""
        )
    counts = active_counts.get(month, {})
    row.update({
        "active_equity": str(counts.get("equity", "")),
        "active_bond": str(counts.get("bond", "")),
        "active_commodity": str(counts.get("commodity", "")),
        "active_currency": str(counts.get("currency", "")),
        "active_sectors": str(counts.get("sectors", "")),
    })
    main_rows.append(row)
  main_fields = ["month"]
  for variant in VARIANTS:
    main_fields.extend(
        f"{variant}_{field}" for field in
        ("gross_return", "net_return", "cash_collateral_return", "portfolio_vol_scalar",
         "gross_exposure", "turnover", "transaction_cost")
    )
  main_fields.extend(["active_equity", "active_bond", "active_commodity", "active_currency",
                      "active_sectors"])
  write_rows(args.output / "managed-futures-monthly.csv", main_rows, main_fields)

  annual_rows, annual_fields = build_annual_rows(targeted)
  write_rows(
      args.output / "managed-futures-annual.csv", annual_rows, annual_fields,
  )

  sector_rows = []
  for month, values in sorted(sectors["mf_1_6_12"].items()):
    counts = active_counts[month]
    sector_rows.append({
        "month": month,
        "equity_raw_return": f"{values.get('equity', math.nan):.12g}"
        if "equity" in values else "",
        "bond_raw_return": f"{values.get('bond', math.nan):.12g}"
        if "bond" in values else "",
        "commodity_raw_return": f"{values.get('commodity', math.nan):.12g}"
        if "commodity" in values else "",
        "currency_raw_return": f"{values.get('currency', math.nan):.12g}"
        if "currency" in values else "",
        "active_equity": counts["equity"],
        "active_bond": counts["bond"],
        "active_commodity": counts["commodity"],
        "active_currency": counts["currency"],
        "active_sectors": counts["sectors"],
    })
  write_rows(
      args.output / "managed-futures-sectors-monthly.csv", sector_rows,
      ["month", "equity_raw_return", "bond_raw_return", "commodity_raw_return",
       "currency_raw_return", "active_equity", "active_bond", "active_commodity",
       "active_currency", "active_sectors"],
  )

  # Ajoute aux positions le scalar final de la variante combinee.
  position_rows = []
  for row in position_audit:
    target = targeted["mf_1_6_12"].get(row["month"])
    if not target:
      continue
    scalar = target["portfolio_vol_scalar"]
    row = dict(row)
    row["portfolio_vol_scalar"] = f"{scalar:.12g}"
    row["final_weight"] = f"{float(row['raw_portfolio_weight']) * scalar:.12g}"
    position_rows.append(row)
  write_rows(
      args.output / "managed-futures-positions-monthly.csv", position_rows,
      ["month", "asset_id", "sector", "signal_1m", "signal_6m", "signal_12m",
       "signal_3m", "combined_signal", "annualized_vol", "asset_leverage", "sector_weight",
       "raw_portfolio_weight", "portfolio_vol_scalar", "final_weight"],
  )

  summaries = build_summaries(targeted)
  summary_fields = [
      "variant", "return_kind", "period", "first_month", "last_month", "months",
      "cagr", "annualized_mean", "annualized_vol", "sharpe_zero_cash",
      "max_drawdown", "positive_months",
  ]
  write_rows(args.output / "managed-futures-summary.csv", summaries, summary_fields)

  # Le comparatif sans mois saute quantifie l'artefact de chevauchement produit
  # par les observations en moyenne mensuelle. Ce n'est pas la serie canonique.
  diagnostic_targeted = {args.signal_skip_months: targeted}
  if args.signal_skip_months != 0:
    (raw_no_skip, weights_no_skip, _sectors_no_skip, _signals_no_skip,
     _counts_no_skip, _audit_no_skip) = build_raw_variants(
         months, markets, 0, args.sector_weighting,
     )
    diagnostic_targeted[0] = {
        variant: target_and_cost(
            months, raw_no_skip[variant], weights_no_skip[variant],
            usd_collateral, args.add_usd_collateral,
            args.annual_fee, args.transaction_bps,
        )
        for variant in VARIANTS
    }
  diagnostic_rows = []
  for skip, values in sorted(diagnostic_targeted.items()):
    for row in build_summaries(values):
      if row["return_kind"] != "gross" or row["period"] != "full":
        continue
      diagnostic_rows.append({"signal_skip_months": skip, **row})
  write_rows(
      args.output / "signal-lag-diagnostic.csv", diagnostic_rows,
      ["signal_skip_months", *summary_fields],
  )
  if 0 in diagnostic_targeted:
    no_skip_rows = []
    for month in sorted({month for values in diagnostic_targeted[0].values()
                         for month in values}):
      row = {"month": month}
      for variant in VARIANTS:
        values = diagnostic_targeted[0][variant].get(month)
        for field in ("gross_return", "net_return"):
          row[f"{variant}_{field}"] = (
              f"{values[field]:.12g}" if values else ""
          )
      no_skip_rows.append(row)
    no_skip_fields = ["month", *[
        f"{variant}_{field}" for variant in VARIANTS
        for field in ("gross_return", "net_return")
    ]]
    write_rows(
        args.output / "managed-futures-no-skip-monthly.csv",
        no_skip_rows, no_skip_fields,
    )

  combined = targeted["mf_1_6_12"]
  combined_months = sorted(combined)
  avg_turnover = statistics.fmean(combined[month]["turnover"]
                                  for month in combined_months) * 12
  avg_exposure = statistics.fmean(combined[month]["gross_exposure"]
                                  for month in combined_months)
  avg_cost = statistics.fmean(combined[month]["transaction_cost"]
                              for month in combined_months) * 12
  full_gross = next(row for row in summaries
                    if row["variant"] == "mf_1_6_12"
                    and row["return_kind"] == "gross" and row["period"] == "full")
  full_net = next(row for row in summaries
                  if row["variant"] == "mf_1_6_12"
                  and row["return_kind"] == "net" and row["period"] == "full")
  since_2000 = next(row for row in summaries
                    if row["variant"] == "mf_1_6_12"
                    and row["return_kind"] == "gross"
                    and row["period"] == "2000-2025")
  since_2010 = next(row for row in summaries
                    if row["variant"] == "mf_1_6_12"
                    and row["return_kind"] == "gross"
                    and row["period"] == "2010-2025")
  no_skip = next((row for row in diagnostic_rows
                  if row["signal_skip_months"] == 0
                  and row["variant"] == "mf_1_6_12"), None)
  report = [
      "PROXY MANAGED FUTURES 1/6/12",
      f"Donnees : {args.input}",
      f"Collateral USD : {args.collateral_input} ({'ajoute au NAV' if args.add_usd_collateral else 'non ajoute'}).",
      ("P&L obligations convertis sans principal FX : oui"
       if args.futures_pnl_fx else "P&L actions/obligations convertis au spot USD : oui"
       if args.normalize_local_pnl_to_usd else "P&L locaux conserves : sensibilite non normalisee"),
      f"Periode ciblee : {combined_months[0]} -> {combined_months[-1]} ({len(combined_months)} mois)",
      f"Univers : {args.universe_profile} ({', '.join(sorted(UNIVERSE_PROFILES[args.universe_profile]))}).",
      *((f"Transition actions : sorties apres {EQUITY_TRANSITION_END} lorsque les devises H.10 sont disponibles.",)
        if args.universe_profile == "historical_equity_transition" else ()),
      f"Ponderation sectorielle : {args.sector_weighting}.",
      ("Signal : moyenne egale des signes du momentum compose 1, 6 et 12 mois; "
       f"{args.signal_skip_months} mois complet(s) saute(s) pour les prix mensuels moyens; "
       "les devises H.10 de fin de mois utilisent t-1."),
      f"Volatilite : {VOL_WINDOW} mois, minimum {MIN_VOL_OBSERVATIONS}; cible marche {ASSET_VOL_TARGET:.0%}, portefeuille {PORTFOLIO_VOL_TARGET:.0%}.",
      f"Caps : levier marche {MAX_ASSET_LEVERAGE:.1f}x, scalar portefeuille {MAX_PORTFOLIO_SCALAR:.1f}x.",
      f"Couts nets : frais {args.annual_fee:.2%}/an + {args.transaction_bps:.1f} pb par unite de turnover.",
      "",
      f"Combine brut : CAGR {float(full_gross['cagr']):.2%}, vol {float(full_gross['annualized_vol']):.2%}, Sharpe(0) {float(full_gross['sharpe_zero_cash']):.2f}, max DD {float(full_gross['max_drawdown']):.2%}.",
      f"Combine net  : CAGR {float(full_net['cagr']):.2%}, vol {float(full_net['annualized_vol']):.2%}, Sharpe(0) {float(full_net['sharpe_zero_cash']):.2f}, max DD {float(full_net['max_drawdown']):.2%}.",
      f"Depuis 2000 brut : CAGR {float(since_2000['cagr']):.2%}, vol {float(since_2000['annualized_vol']):.2%}, Sharpe(0) {float(since_2000['sharpe_zero_cash']):.2f}.",
      f"Depuis 2010 brut : CAGR {float(since_2010['cagr']):.2%}, vol {float(since_2010['annualized_vol']):.2%}, Sharpe(0) {float(since_2010['sharpe_zero_cash']):.2f}.",
      f"Turnover annualise moyen {avg_turnover:.2f}x; exposition brute moyenne {avg_exposure:.2f}x; cout de transaction moyen {avg_cost:.2%}/an.",
      *((f"Diagnostic sans mois saute : Sharpe(0) brut {float(no_skip['sharpe_zero_cash']):.2f}; ne pas utiliser comme resultat.",) if no_skip else ()),
      "",
      "Le Sharpe(0) n'est pas un Sharpe d'exces: il mesure le rendement total, collateral USD inclus le cas echeant.",
      "Obligations et devises sont des P&L en exces de cash; les commodities sont des P&L spot avec roll explicitement suppose nul.",
      "Le roll futures des commodities demeure inconnu hors segments a contrats observes: aucune courbe n'est inventee.",
      "Le fichier signal-lag-diagnostic.csv publie le comparatif sans mois saute, contamine par le chevauchement des moyennes mensuelles.",
  ]
  (args.output / "VALIDATION.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

  manifest = []
  for path in sorted(args.output.iterdir()):
    if not path.is_file() or path.name == "manifest.csv":
      continue
    data = path.read_bytes()
    manifest.append({
        "file": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
  write_rows(args.output / "manifest.csv", manifest, ["file", "bytes", "sha256"])

  print("\n".join(report))


if __name__ == "__main__":
  main()
