# Proxy managed futures mensuel — variantes MOP, AQR et 1/6/12

Cette stratégie lit directement le snapshot figé de `data/mf-inputs/`. Elle ne
télécharge aucune donnée et ne reconstruit aucune série de marché. Le moteur
vient du projet voisin `CTO_vs_PEA` et régénère à l'octet près
`data/managed-futures-monthly.csv`.

```bash
python3 build/managed_futures/run_managed_futures.py
```

Les résultats sont écrits sous `build/managed_futures/output/` (non versionné ;
`rebuild_all.sh` en copie la série mensuelle dans `data/`) : rendements mensuels,
rendements annuels composés, contributions sectorielles, positions par marché,
statistiques par période et empreintes SHA-256. Le fichier annuel ne conserve
que les années calendaires possédant douze rendements mensuels, afin d'être
directement raccordable à un panel annuel sans fabriquer d'année partielle.

## Signal

Pour chaque marché et chaque mois `t` :

1. calcul des rendements composés sur 1, 3, 6 et 12 mois ; les prix mensuels
   moyens s'arrêtent en `t-2`, les devises H.10 de fin de mois en `t-1` ;
2. transformation de chaque momentum en `-1`, `0` ou `+1` ;
3. publication de deux combinaisons fixes : 1/3/12, utilisée par AQR dans sa
   reconstruction historique, et 1/6/12, la variante initiale de ce projet ;
   leurs signaux sont des moyennes égales des signes ;
4. estimation de la volatilité avec les 36 mois précédents, 24 observations
   au minimum ;
5. exposition inversement proportionnelle à cette volatilité, cible 15 % par
   marché et plafond de levier 4×.

Le profil par défaut, `all_four_sectors`, conserve les actions nationales,
obligations, commodities et devises dès que chaque marché est disponible et
convertible proprement en USD. Les secteurs sont pondérés par inverse de leur
volatilité retardée, plutôt que mécaniquement équipondérés. Ce choix maintient
les actions historiques dans l'univers, au prix assumé qu'elles sont des
indices cash de prix et non des contrats futures. L'or et l'argent appartiennent
aux commodities : ils ne forment pas artificiellement un cinquième secteur
pesant 20 %.

`--universe-profile legacy_three_sector` reproduit l'ancien univers
actions–obligations–commodities ; `all_four_sectors` lui ajoute les devises
pour une sensibilité de type SG Trend Indicator.

`historical_equity_transition` reste disponible comme sensibilité : il retire
les actions après décembre 1970, lorsque les devises H.10 deviennent
disponibles. `--sector-weighting inverse_vol` est la convention par défaut :
les secteurs reçoivent des poids inversement proportionnels à leur volatilité
observée sur les 36 mois précédents ; la règle retombe sur l'équipondération
tant que l'historique est insuffisant.

Enfin, le portefeuille brut est ciblé à 10 % de volatilité avec sa volatilité
retardée de 36 mois et un multiplicateur plafonné à 3×.

Le mois `t-1` est volontairement sauté. Une grande partie des prix anciens est
une **moyenne mensuelle**, et non une clôture de fin de mois. Utiliser la moyenne
de `t-1` pour prévoir la moyenne de `t` crée un chevauchement temporel et gonfle
très fortement le signal court. Le paramètre `--signal-skip-months 0` permet de
reproduire cette convention naïve uniquement à des fins de diagnostic. Le
comparatif est publié dans `signal-lag-diagnostic.csv`.

## Rendements brut et net

Le fichier `managed-futures-monthly.csv` publie séparément les stratégies 1,
3, 6 et 12 mois, ainsi que les combinaisons 1/3/12 et 1/6/12. Pour chacune :

- `gross_return` : rendement avant frais ;
- `net_return` : rendement brut diminué de 0,85 % par an et de 3 pb par unité
  de turnover ;
- `cash_collateral_return`, `gross_exposure`, `turnover` et multiplicateur de
  ciblage de volatilité.

Le P&L des contrats est exprimé en excès de cash pour les obligations et les
devises. Le moteur ajoute une fois le rendement cash USD au NAV afin de
représenter le collateral ; `--no-add-usd-collateral` permet une sensibilité
sans cette composante. Le fichier de collateral est local et versionné dans
`data/mf-inputs/cash-returns-monthly.csv`.

Par défaut, les rendements d'actions en devise locale sont convertis en USD
avec le spot de fin de mois. Les obligations sont des P&L synthétiques en
excès du cash : seul leur P&L est converti au spot, sans exposition du
principal au change. Cette convention correspond à un contrat futures
collatéralisé en USD; un P&L local nul reste nul lorsque la devise bouge.
Le spot est lu dans `data/mf-inputs/fx-spot-returns-monthly.csv`.
Il est distinct du rendement des forwards qui constituent le secteur devises.
Lorsqu'un spot USD n'est pas disponible, le marché étranger est exclu de ce
mois : il n'est jamais traité par défaut comme un rendement USD.
`--no-futures-pnl-fx` rétablit l'ancienne convention qui exposait aussi le
principal synthétique; elle est conservée seulement comme sensibilité.

Les paramètres de coût sont modifiables avec `--annual-fee` et
`--transaction-bps`.

## Limites importantes

- six devises sont modélisées comme forwards synthétiques (spot H.10 de fin de
  mois + différentiel de taux courts) ;
- la conversion USD limite les actions et obligations étrangères à la
  disponibilité du spot H.10 : elle réduit donc volontairement l'univers avant
  1971 et pour les devises non encore couvertes ;
- actions nationales en price return, sans dividendes ;
- commodities et métaux en spot return, sans roll, basis ou collateral ;
- obligations en P&L synthétique dix ans, en excès de cash ;
- commodities et métaux ont un roll explicitement supposé nul : il ne faut pas
  interpréter leur niveau de rendement comme un indice futures observé ;
- l'univers s'élargit avec l'histoire des données. Les nombres de marchés
  actifs sont publiés chaque mois ;
- le ciblage de risque n'est révisé que mensuellement avec une fenêtre de 36
  mois. Il ne reproduit pas le désendettement quotidien d'un CTA ;
- le Sharpe publié utilise zéro comme taux de référence : ce n'est donc pas un
  Sharpe d'excès, même si le collateral USD est inclus dans le rendement total.

Ces limites rendent le résultat approprié pour tester la mécanique et la
diversification du trend, pas encore pour annoncer la performance historique
d'un produit futures investissable.

## Validation externe

La comparaison aux indices SG CTA, SG Trend et BTOP50 et aux fonds cotés est
produite par `paper/build_mf_benchmark_data.py` et `paper/build_mf_pack_matrix.py`
(annexe B du papier). Sur 2000-2025, la corrélation mensuelle de la combinaison
1/6/12 vaut environ 0,51 avec SG CTA, 0,49 avec SG Trend et 0,53 avec BTOP50.

`build/mf_excess_return_check.py` reconstruit la série avec des rendements
cohérents avec des futures (actions dividendes inclus et en excès du cash
local, commodities en excès du cash USD) : l'écart annuel moyen est de
−0,05 point et les résultats du papier bougent de quelques dixièmes de point
au plus (`results/audit/mf_excess_return_check.json`).
