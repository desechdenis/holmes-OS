# Protocole d'extinction Holmes — 48 heures

## Objectif

Démontrer que Holmes peut rester éteint pendant 48 heures continues sans effet
sur le fonctionnement domestique, les automatismes, les données canoniques ou
les services essentiels. Ce test valide l'extinction réversible ; il n'autorise
pas à lui seul la suppression définitive des données.

Le test doit être exécuté par l'opérateur de l'infrastructure. Le dépôt fournit
la méthode et les critères, pas l'observation du domicile.

## Préconditions

- Holmes a été réellement raccordé aux usages que l'on souhaite éprouver. Un test
  réalisé avant toute intégration est non concluant.
- L'inventaire des contacts sortants du dépôt est à jour.
- L'inventaire Body correspondant est validé séparément par son opérateur.
- Une sauvegarde hors dépôt des données locales existe et son checksum a été
  vérifié.
- L'état initial est sain : aucune panne préexistante susceptible de fausser le
  résultat n'est ouverte.
- Une fenêtre de 48 heures représentative est choisie, incluant au moins une nuit
  et les automatismes quotidiens habituels.
- L'opérateur sait comment restaurer Holmes, mais aucune restauration automatique
  n'est configurée.

## Référence avant extinction

À `T-30 min`, consigner dans un journal daté :

```text
Commit Holmes : <sha-factice>
Début prévu : <YYYY-MM-DD HH:MM TZ>
Fin prévue   : <YYYY-MM-DD HH:MM TZ>
Archive      : <archive-factice.tar.gz>
SHA-256      : <checksum-factice>
Observateur  : <rôle-factice>
```

Capturer sans secret :

- les processus et services Holmes actifs ;
- les ports ouverts par Holmes ;
- le compteur ou journal disponible des appels externes Holmes ;
- les erreurs déjà présentes dans les systèmes essentiels ;
- l'état des automatismes et fonctions domestiques retenus par l'opérateur ;
- le nombre et l'horodatage des fichiers ou propositions produits par Holmes.

Ne pas copier de jeton, d'adresse interne, de nom d'hôte ou de donnée personnelle
dans le rapport public.

## Déclenchement à T0

1. Arrêter les workers vocaux ou terminaux lancés manuellement.
2. Exécuter `./jarvis service-stop` puis vérifier son résultat.
3. Empêcher tout redémarrage automatique pendant la fenêtre, sans supprimer les
   données ni révoquer les accès.
4. Vérifier l'absence de processus Holmes et de port appartenant à Holmes.
5. Noter l'heure exacte de la dernière activité sortante attribuable à Holmes.

Commandes locales indicatives :

```bash
pgrep -af 'holmes|jarvis|livekit'
lsof -nP -iTCP -sTCP:LISTEN
```

Une correspondance doit être interprétée : un nom similaire ne prouve pas qu'un
processus appartient à Holmes.

## Observations pendant les 48 heures

Effectuer un contrôle à `T+1 h`, `T+6 h`, `T+12 h`, `T+24 h`, `T+36 h` et
`T+48 h`, ainsi qu'après tout incident. Pour chaque contrôle, consigner :

| Heure | Holmes arrêté | Aucun redémarrage | Aucun trafic Holmes | Maison nominale | Données inchangées | Incident/commentaire |
| --- | --- | --- | --- | --- | --- | --- |
| T+1 h | oui/non | oui/non | oui/non | oui/non | oui/non | ... |

L'observation « maison nominale » est remplie depuis la checklist Body privée.
Le dépôt ne reproduit ni sa topologie ni ses identifiants.

Les actions domestiques ordinaires doivent continuer à être utilisées normalement
pendant la fenêtre. Ne pas provoquer d'événement dangereux uniquement pour tester
Holmes.

## Critères de réussite

Le test est réussi uniquement si les huit conditions suivantes sont vraies :

1. aucun processus Holmes ne redémarre pendant 48 heures ;
2. aucun port ou worker attribuable à Holmes ne réapparaît ;
3. aucun appel sortant attribuable à Holmes n'est observé après la période de
   vidange normale des connexions déjà ouvertes ;
4. aucune automatisation ni fonction domestique ne devient indisponible, retardée
   ou dégradée du fait de l'absence de Holmes ;
5. aucun système essentiel n'attend une réponse, un état ou une entité Holmes ;
6. aucune donnée canonique n'est perdue, déplacée ou rendue illisible ;
7. aucune nouvelle écriture ou proposition Holmes n'apparaît pendant l'arrêt ;
8. aucune intervention de maintenance n'est nécessaire pour compenser l'absence
   de Holmes.

Une absence de trafic sans observation fonctionnelle du domicile ne suffit pas.
Inversement, un domicile fonctionnel avec un processus Holmes redémarré à l'insu
de l'opérateur ne valide pas le test.

## Échec et arrêt anticipé

Arrêter le test, conserver les preuves et restaurer Holmes seulement si cela est
nécessaire lorsqu'un des événements suivants survient :

- une fonction essentielle dépend effectivement de Holmes ;
- un processus Holmes redémarre automatiquement ;
- un système tente de joindre Holmes ou bloque en l'attendant ;
- une perte ou corruption de données est suspectée ;
- un incident de sécurité ou de sûreté apparaît.

Documenter la cause, le moment, l'impact et la restauration. Le test suivant doit
repartir de `T0` après correction ; les heures déjà écoulées ne sont pas cumulées.

## Clôture

À `T+48 h`, joindre au rapport :

- le journal complet des contrôles ;
- la preuve d'absence de redémarrage ;
- la synthèse de l'observation réseau disponible ;
- la validation signée de la checklist Body privée ;
- la comparaison des données et propositions avant/après ;
- la décision : `réussi`, `échoué` ou `non concluant`.

Après un succès, choisir explicitement entre redémarrer Holmes, prolonger
l'observation ou appliquer `scripts/holmes_uninstall.md`. Aucune de ces actions
n'est automatique.
