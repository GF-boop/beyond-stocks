**Revue de main-styled — préparation d’une soumission au Journal of Portfolio Management**

Guillaume Flament — note de lecture du 5 septembre 2026.

**Avis général : projet prometteur, mais révision substantielle nécessaire avant soumission.** Le résultat mérite d’être développé : dans cette adaptation publique du cadre ACO, plusieurs allocations diversifiées améliorent simultanément la probabilité d’épuisement du portefeuille et l’épargne équivalente, y compris face à des actions utilisant le même financement externe. La faiblesse principale est la distance qui subsiste entre ce résultat conditionnel à une reconstruction historique et une conclusion suffisamment validée pour guider l’allocation d’un praticien.

Cette appréciation est mon jugement de lecteur, pas une prédiction de décision éditoriale. J’ai lu le texte et les annexes LaTeX, examiné les tableaux inclus, les principaux fichiers de résultats et certains scripts de construction et d’évaluation. Le PDF comporte 38 pages, annexes et références comprises. Deux tests existants de comptabilité du levier passent. Je n’ai pas reconstruit les données depuis les fournisseurs, reproduit les grandes simulations, ni audité intégralement le moteur mensuel amont. Les chiffres ci-dessous sont des résultats archivés vérifiés, pas de nouvelles estimations indépendantes.

**Ce qui est déjà solide et doit être conservé**

- Les comparaisons à exposition identique répondent à une objection essentielle : le gain ne vient pas seulement d’un accès au financement absent chez le benchmark.
- Les ablations à exposition constante permettent de discuter les compositions, avec une reconnaissance explicite du fait que leurs effets ne sont pas additifs.
- Le papier distingue correctement les intervalles Monte Carlo de l’incertitude historique. Il reconnaît également le caractère rétrospectif des exclusions et conserve le panel brut.
- Les scénarios sont appariés entre stratégies ; les paramètres, graines et sorties sont largement documentés.
- Les résultats défavorables sont présents : à 100 % d’exposition, les familles diversifiées demandent davantage d’épargne pour égaler l’utilité d’ACO. Cela renforce la crédibilité du travail.
- Les annexes comportent déjà des contrôles mensuels de marge, des régressions contre des indices et fonds de trend following, ainsi que des sensibilités de préférences. Les recommandations ci-dessous prolongent ces contrôles ; elles ne supposent pas qu’ils sont absents.

**1. Priorité critique — valider économiquement la poche managed futures**

Preuves : section 3.2 ; annexe B, notamment B.1 et B.3 ; `figures/mf_diagnostics.tex` ; `../figures/mf_pack_regressions.tex`.

Le proxy combine des indices actions sans dividendes, des obligations synthétiques et des prix spot de matières premières sans carry ni roll. Certaines séries sont des prix de gros mensuels : il faut aussi établir si les observations sont des moyennes de période ou des prix de fin de mois, et quand elles étaient disponibles. Ces différences ne sont pas de simples frais que l’on peut nécessairement corriger par une constante. Leur effet sur la performance est à mesurer ; je ne présume pas qu’il soit toujours favorable au proxy.

Sur 1927–2025, le diagnostic américain donne au proxy un rendement réel moyen net de 8,10 %, une volatilité de 14,18 % et une corrélation de 0,05 avec les actions mondiales. Une poche dotée de ces propriétés peut mécaniquement améliorer fortement une allocation avec levier. Il faut établir à quel point ces propriétés survivent à une représentation plus fidèle des instruments négociables.

La validation externe est utile, mais les régressions SG CTA, SG Trend et BTOP50 ont des R² de 0,30–0,34 et des tracking errors de 8,7–11,6 % par an. Cela ne disqualifie pas le proxy : un indice multi-gérants et une règle simple ne doivent pas être identiques. Cela ne valide cependant ni sa prime sur un siècle, ni ses propriétés de queue, ni les gains d’utilité obtenus en le substituant à un produit réel.

Travail à produire :

- Sur une période commune, comparer un proxy fondé sur de vrais rendements de futures et le proxy actuel : rendement excédentaire, volatilité, drawdown, comportement dans les crises et coûts.
- Réévaluer les portefeuilles en remplaçant le proxy par plusieurs benchmarks externes, avec un benchmark actions évalué sur exactement les mêmes dates. Distinguer les données de fonds réellement observées des historiques simulés. Une courte fenêtre ne devient pas une validation d’un siècle de retraite par le seul bootstrap.
- Appliquer des réductions explicites de la prime MF, par exemple 25 %, 50 % et 100 %, en conservant les fluctuations autour de cette prime et la convention de collatéral. Mesurer aussi la sensibilité de la protection en crise. Ce sont des stress tests, pas une prévision.
- Publier le seuil de dégradation de la poche à partir duquel l’épargne équivalente atteint 10 %, avec l’incertitude correspondante.

**Critère de réussite :** le résultat principal reste économiquement significatif avec une représentation et des hypothèses prudentes de la poche, ou la conclusion se resserre explicitement sur les conditions nécessaires à sa réussite.

**2. Priorité critique — mesurer l’incertitude historique du gain**

Preuves : section 4.4 et annexe D, « Historical-sample uncertainty ».

L’intervalle de la différence de ruine, environ −4,97 à −4,03 points, décrit la précision de simulation conditionnelle au panel. Augmenter le nombre de trajectoires le resserrerait sans ajouter une année d’histoire. Les 1 561 lignes ne sont pas 1 561 observations indépendantes, notamment parce que l’or, le MF et une grande partie des paniers mondiaux sont communs aux résidents.

Les fenêtres historiques et omissions de pays sont déjà présentes, mais leurs plages ne quantifient pas la distribution d’incertitude de l’avantage. De plus, les omissions de pays laissent les entrées mensuelles MF inchangées : ce n’est pas un retrait complet de l’influence économique du pays.

Ajouter une couche externe de rééchantillonnage de blocs calendaires qui conserve conjointement les pays et les actifs, puis recalculer à l’intérieur les résultats lifecycle. Le protocole doit préciser le traitement des paniers reconstruits, des lacunes et des transitions de blocs ; un bootstrap indépendant des lignes serait inadéquat. Montrer l’incertitude de Δruine, de Δépargne équivalente et du classement, pour plusieurs longueurs de blocs. Un pilote limité doit d’abord vérifier le coût et la stabilité ; aucune grande campagne n’a été lancée pour cette revue.

Compléter par des omissions de périodes globales et des diagnostics des poids effectifs des années dans les trajectoires. Le raccordement d’un bloc inachevé au début d’une autre série peut modifier ces poids. L’intérêt n’est pas de remplacer arbitrairement ACO, mais de comprendre ce que cette règle produit dans un panel comportant des poches globales communes.

**Critère de réussite :** pouvoir dire si le signe et l’ordre de grandeur du gain résistent à l’incertitude sur l’histoire disponible, et pas uniquement au bruit de simulation.

**3. Priorité élevée — relier l’exposition théorique à une implémentation complète**

Preuves : équations de couverture et de rendement du portefeuille, passage sur les ETF, annexe H sur les marges, `figures/aco_cost.tex`.

Le manuscrit précise correctement que la somme des poches ne mesure pas les positions dérivées internes du MF. Il faut tirer cette distinction jusqu’au bout : 175 % contre 175 % égalise le financement externe défini par l’équation, pas l’ensemble des expositions économiques, besoins de collatéral et risques de liquidité.

Le contrôle mensuel actuel utilise un proxy USD sur 1970–2025, substitue des Treasuries au panier obligataire mondial et compte les franchissements sans liquidation. C’est un diagnostic pertinent, pas une simulation des conséquences économiques d’un appel de marge. L’achat comptant de parts d’ETF évite la marge personnelle, mais ne supprime pas les contraintes internes du fonds.

Construire une implémentation mensuelle récente, cohérente sur un même ensemble d’actifs, avec collatéral, frais, financement et règle explicite de désendettement/réentrée. Comparer l’impact sur la richesse et la consommation, pas uniquement le nombre de franchissements. Distinguer la détention de parts de fonds de l’emprunt direct du ménage, car leurs mécanismes de pertes et de financement diffèrent.

La couverture initiale est algébriquement explicite, mais son prix utilise les rendements annuels réalisés des bills. Un forward négocié en début d’année dépend de taux connus à cette date. C’est une approximation à quantifier avec des taux retardés ou des couvertures mensuelles. De même, les spreads déduits directement des rendements réels doivent être distingués de frais nominaux ensuite déflatés, particulièrement dans les états d’inflation extrême.

Enfin, montrer les seuils de rentabilité en coûts pour la stratégie centrale à 175 %, à la fois en ruine et en épargne équivalente. La table de coûts à 200 % montre déjà 8,13 % de ruine pour l’équipondéré à 300 pb, contre 6,98 % pour ACO sans levier au même panel : la frontière d’échec existe et mérite d’être mise en évidence. La table présente l’épargne équivalente d’ACO, mais pas celle des deux familles diversifiées.

**4. Priorité élevée — comparer la sécurité d’un même objectif de retraite**

Preuves : sections 4.1–4.2 ; annexe F ; `build/compare_lifecycle_utility.py`, fonctions `build_scenario` et `evaluate_batch`.

Chaque stratégie fixe ses retraits à 4 % de sa propre richesse à 65 ans. Sa probabilité de ruine ne répond donc pas directement à la question : « Peut-elle mieux financer le même niveau de vie ? » Un capital plus faible entraîne aussi un objectif de retrait plus faible. Le taux d’épargne équivalent ajoute une comparaison d’utilité pertinente, mais le tableau central met peu en évidence les niveaux de consommation et leurs queues.

Ajouter une expérience à objectif de consommation réel commun, éventuellement exprimé comme taux de remplacement du revenu, et mesurer la probabilité et la durée du déficit, sa sévérité, ainsi que les quantiles de consommation. Conserver l’expérience ACO à 4 % pour la comparabilité. Ajouter une politique de retrait adaptative simple pour vérifier que l’intérêt du MF ne dépend pas trop d’une rigidité particulière.

Le papier explique déjà que la variation du taux de contribution laisse la ruine inchangée par homothétie. Ce contrôle est utile pour l’utilité, mais ne constitue pas une validation indépendante forte de la robustesse de la ruine. Les tests les plus informatifs varient ce qui casse cette homothétie ou change l’objectif économique.

L’épargne équivalente égalise l’utilité de retraite et de legs définie dans le modèle ; elle n’est pas une mesure complète du bien-être sur toute la vie puisque la consommation avant la retraite n’entre pas dans l’agrégateur. Présenter 6,53 % comme une compensation conditionnelle, pas comme un taux d’épargne recommandé.

**5. Priorité élevée — justifier le rôle de chaque poche et le choix de 175 %**

Preuves : section 5.3 ; `results/sleeve_ablation_n10000.json`.

Un résultat particulièrement intéressant est déjà dans les sorties : à 175 %, retirer l’or de la famille équipondérée et redistribuer sa pondération donne 19,81 % de volatilité, 1,83 % de ruine et 5,04 % d’épargne équivalente, contre 25,54 %, 2,48 % et 6,53 % avec quatre poches. Cette amélioration des trois estimations ponctuelles n’établit pas une dominance statistique ou universelle, mais elle appelle une discussion centrale.

Dans la famille proportionnelle, retirer les obligations améliore aussi les estimations de ruine et d’épargne, avec une volatilité plus élevée. Le papier établit donc mieux l’intérêt de certaines compositions élargies que la nécessité d’un portefeuille précisément composé d’actions, obligations, or et MF.

Ne pas sélectionner simplement le nouveau gagnant. Conserver les familles comme règles illustratives, présenter les compositions simples non dominées dans les métriques étudiées, et identifier les états où l’or ou les obligations apportent une protection spécifique. Il serait particulièrement utile de montrer des rendements composés, probabilités de perte réelle et dépendances à 5, 10 et 20 ans : le lien avec le résultat long horizon d’ACO serait beaucoup plus direct qu’une comparaison essentiellement fondée sur la volatilité annuelle.

Le texte dit que les poids sont fixés avant évaluation. Le manifeste garantit leur absence d’estimation automatique à partir des moments, pas leur indépendance vis-à-vis des recherches antérieures de l’auteur. Le README archivé reconnaît d’ailleurs l’absence de préenregistrement. Expliquer comment les familles, les horizons de signal et le niveau central de 175 % ont été choisis. Une validation temporelle ultérieure avec des règles désormais gelées est utile ; des fenêtres déjà examinées restent des sensibilités rétrospectives.

**6. Priorité élevée — traiter les observations extrêmes comme un problème de mesure et de régime**

Preuves : sections 3.1 et 5.5 ; diagnostics Italie 1942 et France 1946.

L’Italie 1942 représente 48,35 % de la dispersion quadratique du benchmark et 52,25 % de celle de l’équipondéré 175 %. Le diagnostic d’influence est bienvenu. La prochaine preuve à apporter concerne la nature des observations : changements d’unité, taux officiel ou accessible, dates de mesure, inflation et éventuelles restrictions de transfert. Retirer la ligne ou winsoriser ne tranche pas ces questions.

Produire pour chaque événement majeur une fiche source et un recalcul manuel de la conversion, distinguant erreur documentée, rendement économique extrême plausible et prix non négociable. Une erreur démontrée peut justifier une correction ; un résultat gênant ne la justifie pas.

L’or administré, les contraintes de change et le caractère synthétique du MF compliquent une interprétation « portefeuille historiquement investissable depuis 1927 ». Le cadre peut rester une simulation prospective à partir d’états historiques, mais il faut expliciter les hypothèses nécessaires pour transporter ces états vers une implémentation moderne. Montrer aussi le résultat central à 175 % sur les fenêtres tardives : le tableau principal des fenêtres présente actuellement surtout 200 %.

**7. Priorité élevée — livrer une chaîne de reproduction autonome et une version unique**

Preuves : section 3.1 ; annexe G ; `README.md` local ; `../../REPRODUCIBILITY.md` ; `build/trend_costs.py`.

Le texte annonce une reproduction à partir de sources publiques, tandis que l’annexe précise que le moteur amont du MF n’est pas inclus dans le répertoire du papier. Reproduire les résultats à partir d’un snapshot fourni et reconstruire le snapshot depuis les sources sont deux niveaux distincts. Le second reste à rendre disponible ou à identifier par une dépendance publique, versionnée et exécutable.

La documentation racine de reproductibilité renvoie encore à des tables et calibrations anciennes, notamment un optimum actions voisin de 30/70, alors que le manuscrit annonce 25/75. Le README local distingue certaines archives, mais le lecteur doit pouvoir reconstruire uniquement la version soumise sans devoir départager plusieurs conventions.

Le coût MF offre un exemple concret à harmoniser : le moteur lifecycle déduit un coût annuel fondé sur le turnover moyen de tout le snapshot, tandis que certains diagnostics externes appliquent les coûts mensuels réalisés. L’annexe indique environ 0,19 point de différence de moyenne. Ce n’est pas une preuve d’invalidation du classement, mais la dépendance temporelle des coûts importe pour une étude de risque de séquence. Réévaluer le cas central avec les mêmes coûts mensuels composés que la validation externe serait un contrôle utile.

Livrable attendu : version du code figée, empreintes des entrées, environnement, une commande de reproduction depuis le snapshot, une commande séparée pour sa reconstruction, et un manifeste reliant chaque tableau à la configuration exacte. Les liens `blob/main` sont utiles pour naviguer mais doivent être complétés par une version immuable. Distinguer explicitement les données publiques des entrées externes soumises à licence.

**8. Priorité éditoriale — formuler une contribution plus précise et resserrer le texte**

Le meilleur positionnement me paraît être : **dans quelles conditions une diversification entre classes d’actifs, financée de façon réaliste, améliore-t-elle le compromis entre épargne nécessaire et sécurité de la retraite ?** Les seuils de coût et de prime MF seraient alors des résultats majeurs, au même titre que le gain au scénario central.

La littérature démontre déjà l’intérêt du trend following pour le risque de séquence et documente son histoire longue. Le papier doit revendiquer précisément ce qu’apportent son cadre de ménage, son panel, ses comparaisons à exposition constante et sa mesure d’épargne équivalente. Éviter une affirmation absolue de première contribution sans revue bibliographique plus exhaustive. La discussion de Clare et coauteurs doit reconnaître qu’ils étudient déjà explicitement la décumulation, même sans le même modèle lifecycle complet.

L’article ACO accessible lors de cette revue est daté du 18 novembre 2024 ; la bibliographie locale cite la révision du 10 juillet 2025. Je n’ai donc pas validé ligne par ligne la fidélité à cette révision exacte. Archiver la version de référence et ajouter une table de rapprochement : univers, dates, fréquence, distributions de revenus et longévité, conventions de rendement, ruine, consommation et utilité. Retrouver un classement qualitatif est une adaptation cohérente, pas une réplication quantitative complète.

Réorganisation proposée du corps du papier : une question centrale ; un bref rapprochement avec ACO ; les données et hypothèses indispensables ; une figure de compromis épargne–sécurité ; une attribution des mécanismes ; des seuils d’échec ; les implications pratiques. Les diagnostics d’exclusion détaillés et les variantes anciennes peuvent rester dans le supplément. Les trois questions de la section 2.2 sont actuellement plus larges que les réponses mises en avant ; réduire ces promesses ou restituer leurs résultats distincts.

Le résumé comporte trop de chiffres et accorde beaucoup de place au panel filtré. Garder un résultat principal avec ses conditions, une preuve de robustesse décisive et une limitation matérielle. Éviter de répéter les mêmes chiffres dans le résumé, l’introduction, les résultats et plusieurs paragraphes de conclusion.

Les consignes PMR publiées indiquent une longueur cible de 4 000 mots hors résumé, exhibits et références ; c’est une cible éditoriale, pas une équivalence en pages ni une limite que j’ai vérifiée sur le manuscrit. Cette indication provient du document officiel indexé de 2023 et de la page de soumission PMR indexée ; leur ouverture directe a été bloquée lors de la vérification. Vérifier le formulaire JPM applicable au moment de la soumission avant de régler les détails de format.

**Ordre de travail recommandé**

| Étape | Livrable concret | Décision éclairée |
|---|---|---|
| 1 | Version reproductible figée et audit des principales conversions et conventions MF | Les résultats publiés correspondent-ils à une chaîne cohérente ? |
| 2 | Substitution de la poche MF, réduction de sa prime et comparaison sur période commune | L’avantage dépend-il d’une reconstruction trop favorable ? |
| 3 | Incertitude historique et diagnostic de pondération des périodes | Le signe et l’ampleur du gain sont-ils suffisamment établis ? |
| 4 | Implémentation mensuelle et seuils de coût, objectif de consommation commun | Le gain se traduit-il en amélioration praticable pour le ménage ? |
| 5 | Réécriture de la contribution, des exhibits et du résumé | Quel résultat les preuves autorisent-elles réellement à publier ? |

Les trois premiers blocs sont, à mon avis, les plus importants avant une soumission. Une conclusion moins spectaculaire mais assortie d’une frontière claire de validité serait plus convaincante qu’une nouvelle accumulation de variantes favorables. Aucun résultat négatif de ces expériences ne doit être écarté : il peut devenir une contribution pratique sur les limites de la diversification avec levier.

**Sources externes consultées pour situer la revue**

- [PMR, Article Submission Guidelines, document officiel indexé de 2023](https://www.pm-research.com/sites/default/files/2023-03/PMR_Article_Submission_Guidelines_2023.pdf) et [page PMR de soumission, consignes communes indexées](https://pmr-journals.pm-research.com/index.php/JAI/about/submissions) : cible de longueur et orientation professionnelle ; accès direct bloqué.
- [Anarkulova, Cederburg et O’Doherty, version du 18 novembre 2024 hébergée par Arizona State University](https://finance-conference.wpcarey.asu.edu/sites/default/files/2025-01/Beyond%20the%20Status%20Quo.pdf) : version consultée, distincte de celle citée dans le manuscrit.
- [Hurst, Ooi et Pedersen, A Century of Evidence on Trend-Following Investing, AQR, 2017](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing) : portée historique et antériorité de la recherche sur le trend following.
- [Clare et coauteurs, notice du working paper hébergé par York](https://www.york.ac.uk/media/economics/documents/discussionpapers/2016/1611.pdf) : travaux antérieurs sur risque de séquence et décumulation ; texte intégral York non récupéré lors de cette revue.
