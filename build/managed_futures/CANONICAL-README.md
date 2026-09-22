# Snapshot mensuel canonique pour les managed futures

> Copie du README du projet `CTO_vs_PEA`. Ce dépôt ne contient que les
> fichiers lus par le moteur, dans `data/mf-inputs/` :
> `all-assets-monthly.csv`, `cash-returns-monthly.csv`,
> `fx-spot-returns-monthly.csv`, `series-metadata.csv`, `source-segments.csv`
> et `snapshot-manifest.csv`. Les autres fichiers cités ci-dessous restent dans
> `CTO_vs_PEA`.

Le répertoire local `data/` contient les séries mensuelles directement
consommables par les simulations. **Aucun téléchargement et aucune pipeline ne
sont nécessaires à l'usage** : le fichier principal est
`data/all-assets-monthly.csv`.

Le script `build_canonical_assets.py` est conservé uniquement pour l'audit de
la construction et la production d'une future version. Il est intégralement
hors ligne.

## Périmètre figé

- fréquence : mensuelle ;
- période : janvier 1921 à décembre 2025 ;
- valeurs : rendements nominaux décimaux (`0.01` = 1 %) ;
- aucune inflation, aucun frais et aucune interpolation ;
- le premier rendement de chaque nouveau segment de source est manquant : un
  signal ne peut donc jamais traverser silencieusement une couture.

## Fichiers prêts à lire

| Fichier | Contenu |
|---|---|
| `all-assets-monthly.csv` | Format long universel avec classe, marché, nature du rendement, segment source et appartenance à l'univers par défaut |
| `equity-returns-monthly.csv` | 18 indices actions nationaux en **price return**, donc sans dividendes |
| `bond-returns-monthly.csv` | 18 proxys souverains dix ans en excès de cash, avec portage et variation de prix |
| `commodity-returns-monthly.csv` | 19 séries spot/cash de matières premières |
| `precious-metals-returns-monthly.csv` | Or depuis 1921 et argent depuis 1960 |
| `currency-returns-monthly.csv` | Six forwards synthétiques : spot H.10 fin de mois et différentiel de taux courts |
| `cash-returns-monthly.csv` | Rendements mensuels de cash par devise/pays, déjà décalés d'un mois |
| `cash-return-sources-monthly.csv` | Source de chaque observation de cash (OECD mensuel ou fallback JST/GMD) |
| `fx-spot-returns-monthly.csv` | Variations spot USD des six devises H.10, reservees a la conversion de P&L locaux |
| `equity-benchmarks-monthly.csv` | SPYSIM, VTISIM, VXUSSIM, URTHSIM et VTSIM, exclus par défaut car recouvrants |
| `bond-benchmarks-monthly.csv` | SHYSIM, IEISIM, IEFSIM et TLTSIM, exclus par défaut |
| `series-metadata.csv` | Dictionnaire des séries et limites essentielles |
| `source-segments.csv` | Provenance et transformation de chaque segment |
| `flagged-outliers.csv` | Mouvements extrêmes conservés mais signalés pour les sensibilités |
| `snapshot-manifest.csv` | Taille, période et SHA-256 de chaque fichier |
| `VALIDATION.txt` | Résumé des contrôles et comparaisons |

Les données OECD et NBER sont publiques et doivent être citées.

## Choix de construction

### Actions

L'univers par défaut ne contient que les 18 pays du panel JST. Pour les
États-Unis, le Royaume-Uni, l'Allemagne et la France, des indices NBER
prolongent l'histoire avant les séries OECD. Tous sont traités en **indices de
cours** : ajouter SPYSIM comme dix-neuvième marché introduirait à la fois les
dividendes et un double comptage des États-Unis.

Les benchmarks Testfol total-return restent disponibles pour les contrôles et
les sensibilités, avec `default_universe=no`.

La couverture demeure mince avant 1960 : fin 1921, le snapshot contient trois
marchés actions, trois obligations, quatre matières premières et l'or. Il ne
faut donc pas comparer mécaniquement la volatilité d'un « secteur » de trois
marchés à celle d'un secteur moderne de dix-huit marchés sans règle de
normalisation explicite.

### Obligations

Un taux n'est jamais utilisé comme un rendement. Les taux souverains sont
transformés en rendement d'un titre au pair de maturité initiale dix ans : le
coupon est le taux du mois précédent, puis les vingt flux semestriels restant
après un mois sont actualisés au nouveau taux. Cette formule accepte les taux
négatifs européens.

Avant les séries OECD :

- États-Unis : taux longs NBER depuis 1919, modélisés avec une maturité proxy
  de dix ans ;
- Royaume-Uni : Consol jusqu'en 1934, puis série dix ans Bank of England ;
- France : prix observé de la rente perpétuelle 3 % jusqu'en 1940.

Ces segments apportent de la profondeur, mais ne sont ni des indices
obligataires observés homogènes ni des historiques de futures.

Pour représenter un contrat obligataire, le rendement cash trois mois de la
devise est ensuite soustrait. Les fixings mensuels OECD/FRED ont priorité ;
avant leur disponibilité, le taux court nominal annuel JST/GMD est appliqué au
cours de l'année suivante, de sorte qu'aucune publication annuelle future ne
sert au mois courant. `cash-return-sources-monthly.csv` rend ce choix
auditable, observation par observation.

### Convention de devise

Les actions et obligations nationales restent des rendements en devise locale
dans `all-assets-monthly.csv`. Le fichier `fx-spot-returns-monthly.csv` isole
la variation spot USD des devises H.10, distincte du rendement de forward du
secteur devises. Le moteur managed futures l'utilise pour convertir les P&L
locaux disponibles en USD ; il retire un marche etranger lorsque son spot USD
est indisponible, plutot que de le traiter implicitement comme un P&L USD.

### Matières premières et métaux

Les longues séries NBER/BLS sont relayées, sans rendement au mois de couture,
par le Pink Sheet de la Banque mondiale. Les doublons évidents sont fusionnés :
corn/maize, wheat, sugar et copper ne comptent chacun que pour un marché.

L'or emploie le prix officiel américain répété mensuellement jusqu'en 1959,
puis le prix mensuel de la Banque mondiale. La hausse libre de 1968 est donc
préservée. Aucun frais de garde n'est incorporé.

Limite fondamentale : ces séries sont des prix spot/cash. Elles permettent de
construire un **proxy** de tendance, pas de récupérer rétroactivement le carry,
la base et les rolls de contrats futures inexistants ou non archivés.

### Devises et collateral

Les six marchés AUD, CAD, EUR, JPY, CHF et GBP proviennent des fixings H.10
quotidiens de la Réserve fédérale, agrégés par **dernière observation publiée
du mois** et convertis en USD par unité de devise étrangère. Ils peuvent donc
former leur signal à `t-1`, sans le chevauchement des indices en moyenne
mensuelle. Le P&L est celui d'un forward synthétique long : rendement spot,
plus rendement cash étranger, moins cash USD. Les trois taux sont tous connus
au mois précédent. Pour la devise EUR, le fixing euro-zone est employé ; les
anciennes devises européennes ne sont pas rétro-construites.

Le moteur MF peut ajouter le cash USD de `cash-returns-monthly.csv` au NAV,
ce qui représente le collateral du portefeuille. Il ne l'ajoute pas une
seconde fois aux contrats, qui sont déjà exprimés en excès de cash.

## Ce qui restera à décider pour le signal MF

Ce snapshot ne contient volontairement aucune règle de stratégie. La prochaine
étape devra fixer le lookback, le retard du signal, l'estimateur de volatilité,
le plafond de levier, le poids sectoriel, le traitement des historiques courts
et les coûts. Les benchmarks recouvrants devront rester exclus de tout comptage
automatique du nombre de marchés.
