# Prise en compte des annotations du 5 septembre 2026

Révision complémentaire à la demande de l'auteur : le diagnostic ciblé
« Italy, all years » a été retiré de l'introduction, de la section des
résultats, du tableau (y compris son intervalle Monte Carlo), de l'annexe et
de la conclusion. Les deux diagnostics d'événements Italie 1942 et
Italie 1942 + France 1946 restent présentés. L'Italie reste dans
l'échantillon principal ; les fichiers de résultats archivés sont conservés.

Les 12 commentaires distincts du PDF annoté ont été traités dans
`main-styled.tex`. L'annotation sur « improve » apparaît deux fois dans
l'historique interne du PDF ; sa dernière version, demandant des références,
a été retenue. Les pages ci-dessous renvoient au PDF avant révision.

Le PDF original est conservé dans `main-styled-annotated-2026-09-05.pdf` et
le source avant modification dans `main-styled-before-comments-2026-09-05.tex`.
Cette révision est éditoriale : elle s'appuie sur les résultats archivés,
sans modifier les modèles ni relancer les simulations.

| Page | Commentaire | Modification |
| --- | --- | --- |
| 1 | « lifecycle investors » peu clair | Remplacé par « households saving for retirement », qui précise la population et l'objectif du modèle. |
| 1 | Préciser les 6,53 % d'épargne | L'abstract parle désormais explicitement d'un taux d'épargne équivalent en utilité, exprimé en pourcentage du revenu du travail. |
| 2 | Phrase obscure sur Markowitz et Asness | Explication concrète du rôle des corrélations chez Markowitz et du financement d'un portefeuille diversifié chez Asness. |
| 2 | Préciser « improve » et ajouter des références | Distinction entre variance annuelle, probabilité d'épuisement des actifs et épargne équivalente ; référence à Moskowitz et al. sur le comportement du suivi de tendance en marchés extrêmes. Aucune nouvelle affirmation de dominance de la distribution ou de réduction des drawdowns. |
| 2 | Justifier le 1/N | Ajout de DeMiguel, Garlappi et Uppal (2009), avec la portée empirique de leur résultat et sans présenter notre équipondération comme optimale. |
| 2 | Expliquer simplement le 60/40/25/25 | Point de départ 60/40, puis emprunt de 50 % du capital pour ajouter 25 % d'or et 25 % de managed futures ; mise à l'échelle proportionnelle aux autres niveaux. |
| 2 | Dire que le 33/67 est quasi optimal sur nos données | Ajout dans l'introduction du meilleur mix 25/75 et de son épargne équivalente de 9,96 %, contre 10 % pour 33/67, en précisant le domaine de la grille. |
| 3 | Expliquer pourquoi exclure Italie/France | Introduction de la concentration de variance avant les exclusions : Italie 1942 représente 48,35 % de la somme des écarts quadratiques du benchmark. Il s'agit d'une part de variance, pas de volatilité. |
| 3 | Dire que le résultat survit aux périodes hors marché | Ajout des résultats du filtre d'accès historique et de stress monétaire. Le texte précise que ce filtre rétrospectif ne prouve pas l'investissabilité de toutes les observations restantes. |
| 3 | Dernière phrase peu compréhensible | Conclusion du paragraphe reformulée : les gains ne se limitent pas à l'histoire ancienne, et leur persistance est la question centrale. |
| 3 | Première question peu centrale | Le change devient un diagnostic secondaire de construction des rendements. |
| 4 | Deuxième question secondaire ; recentrer sur la troisième | La section 2.2 présente une seule question centrale sur les allocations multi-actifs, leur exposition et leur robustesse ; les obligations restent un diagnostic d'interprétation. |

## Vérification des chiffres

- `../../results/grid_equity_n10000.json` : optimum 25/75, taux d'épargne
  équivalent 9,96 %, contre 10 % pour 33/67. Correction des deux anciennes
  mentions de 0,02 point en 0,04 point. La quasi-optimalité concerne la grille
  domestique/internationale sans emprunt, pas tous les portefeuilles possibles.
- `../../results/method_review/variance_concentration.json` : contribution
  d'Italie 1942 à la variance du benchmark de 0,4834907382.
- `figures/panel_full_comparison.tex` : chiffres du panel brut et du panel
  filtré repris sans modification ; chaque panel utilise sa propre utilité
  cible ACO pour l'épargne équivalente.

## Sources consultées pour les formulations bibliographiques

- [Markowitz (1952), Portfolio Selection](https://finance.martinsewell.com/capm/Markowitz1952.pdf) : cadre espérance-variance et diversification.
- [Asness (1996), Why Not 100% Equities](https://www.aqr.com/Insights/Research/Journal-Article/Why-Not--Equities) : séparation entre composition du portefeuille et niveau de risque, comparaison avec un portefeuille équilibré financé.
- [Moskowitz, Ooi et Pedersen (2012), Time Series Momentum](https://fairmodel.econ.yale.edu/ec439/mosk.pdf) : abstract de l'article et résultats sur les marchés extrêmes.
- [DeMiguel, Garlappi et Uppal (2009), Optimal Versus Naive Diversification](https://doi.org/10.1093/rfs/hhm075), [abstract des auteurs sur SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1376199) : 14 modèles, sept jeux de données, absence de supériorité systématique sur le 1/N hors échantillon.

## Validation

Compilation complète par `pdflatex`, `biber`, puis deux passes `pdflatex` :
PDF de 44 pages, sans avertissement LaTeX, référence indéfinie ni dépassement
de boîte dans le journal final. Texte des quatre premières pages relu après
extraction ; pages 1 et 3 contrôlées visuellement. `git diff --check` passe.
