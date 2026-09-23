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
  leur rôle, l'inventaire détaillé des services internes ni l'emplacement des secrets.
- Les exemples utilisent uniquement des valeurs factices.
- Aucune nouvelle intégration externe n'est ajoutée sans besoin régulier établi.

## Réversibilité

Holmes doit pouvoir être arrêté et retiré sans migration des données essentielles
et sans modification du fonctionnement domestique. Deux opérations distinctes
sont prévues :

1. **Extinction** — arrêter les processus API et voix, empêcher leur redémarrage
   automatique, puis vérifier qu'aucun processus Holmes n'écoute ou n'émet.
2. **Retrait** — après une période d'observation concluante, révoquer les jetons,
   supprimer les autorisations et callbacks externes, archiver les données locales
   utiles, puis retirer le code, les environnements et les fichiers de service.

Les interrupteurs applicatifs réduisent la surface, mais ne prouvent pas à eux
seuls l'absence de trafic. Le mode LLM local ne neutralise pas tous les outils,
routes manuelles, téléchargements ni dépendances chargées par le navigateur. Une
extinction garantie repose donc d'abord sur l'arrêt des processus Holmes ; une
preuve renforcée peut être fournie par le pare-feu ou l'observation réseau.

Chaque point de contact doit avoir un propriétaire, une condition d'activation
et une méthode de coupure documentés. L'inventaire du dépôt se trouve dans
`HOLMES_OUTBOUND_CONTACTS.md`; les raccordements propres à l'infrastructure sont
tenus séparément par son opérateur.

Les données canoniques, automatismes et services essentiels restent hors du cycle
de vie de Holmes. La procédure de retrait ne les efface, ne les migre et ne les
reconfigure jamais. Les données locales éventuellement conservées sont archivées
dans un format lisible avant suppression.

La réversibilité est validée par un test d'extinction continu de 48 heures. Une
dépendance, une dégradation domestique ou un redémarrage non sollicité invalide le
test et bloque le retrait définitif.
