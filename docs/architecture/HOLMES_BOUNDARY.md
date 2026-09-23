# Holmes OS — frontière publique

Holmes OS est une interface conversationnelle et un moteur de propositions
optionnel. Il peut lire des informations fournies par les systèmes existants,
les présenter, préparer des plans et produire des propositions réversibles.

Holmes n'est pas une source d'autorité pour la maison. Son arrêt, son absence ou
une erreur de sa part ne doivent modifier ni interrompre le fonctionnement des
systèmes existants.

## Invariants

- Les dépendances sont unidirectionnelles : Holmes peut lire les systèmes
  existants ; aucun système essentiel ne dépend de Holmes, de sa disponibilité
  ou de sa réponse.
- Holmes ne crée aucune dépendance dans les automatisations domestiques.
- L'état domestique est en lecture seule. Aucune commande physique n'est déduite
  ou exécutée implicitement à partir d'une conversation.
- Une donnée produite ou déduite par un modèle n'est jamais promue
  automatiquement en vérité canonique.
- Les écritures automatiques destinées à la mémoire canonique restent des
  propositions séparées jusqu'à validation humaine.
- Une mission reste lisible et modifiable manuellement dans un format texte
  ouvert. Sa préparation et son exécution sont deux décisions distinctes.
- Toute action persistante ou externe doit être explicite, traçable et
  réversible. En cas d'ambiguïté ou d'indisponibilité, Holmes s'abstient.
- Les artefacts créés dans un système partagé sont identifiables comme provenant
  de Holmes.

## Ce que Holmes ne remplace pas

Holmes ne remplace pas les automatismes, la collecte déterministe, la sécurité,
la supervision, la mémoire canonique, le transport vocal ni les mécanismes de
continuité déjà en place. Ces fonctions doivent continuer à fonctionner de
manière autonome.

Le moteur proactif de Holmes consomme des faits déjà établis. Il ne devient pas
un nouveau collecteur et ne transforme pas seul une observation en action.

## Données et publication

- Les secrets, souvenirs personnels, conversations et données d'exploitation ne
  sont jamais versionnés dans ce dépôt public.
- La documentation publique ne décrit pas l'adressage interne, les noms d'hôtes,
  leur rôle, l'inventaire détaillé des services ni l'emplacement des secrets.
- Les exemples utilisent uniquement des valeurs factices.
- Aucune nouvelle intégration externe n'est ajoutée sans besoin régulier établi.

## Réversibilité

Holmes doit pouvoir être arrêté et retiré sans migration des données essentielles
et sans modification du fonctionnement domestique. Les procédures d'installation
et de retrait doivent inventorier chaque point de contact créé par Holmes et
permettre de le supprimer indépendamment.
