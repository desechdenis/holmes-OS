# Cartographie du fork Jarvis OS → Holmes OS

**Statut :** validé pour poursuite de la migration  
**Date de revue :** 2026-09-17

## Position actuelle

Holmes est un prototype fonctionnel avancé construit sur l'architecture en
couches de Jarvis OS. Le cœur d'exécution est conservé ; la mémoire, le contexte
maison, le comportement du modèle local et les intégrations temps réel sont en
cours d'adaptation. Le fork n'est pas encore prêt à être publié.

## KEEP — conserver

- Architecture en couches `kernel → capabilities/providers → engine → interfaces`.
- `bootstrap.Container` comme composition root partagé.
- FastAPI, `SessionManager`, `Gateway` et stockage JSONL des sessions.
- WebSocket de chat et LiveKit pour la voix locale sur le Mac.
- Registre d'outils, bus d'événements, notifications et tâches de fond.
- `Scheduler`, `BackgroundWorker`, routines et moteur proactif comme fondations.
- Contrats injectés pour la mémoire, Calendar et Home Assistant.

## ADAPT — conserver en changeant le comportement

- Identité visible et prompts : Holmes remplace progressivement Jarvis.
- Petit LLM local : prompt compact et préchargement déterministe des faits.
- Soul : mémoire canonique interrogée à chaque tour texte et vocal.
- Home Assistant : contexte d'état en lecture seule ; aucune commande implicite.
- Google Calendar/Gmail : données vivantes prioritaires sur la mémoire historique.
- Telegram : canal réseau explicitement autorisé en mode LLM local.
- Accès LAN : Bearer pour l'API et les appels internes, avec diagnostic du chemin.
- Scheduler : évoluer vers le silence par défaut et les collecteurs déterministes.

## REPLACE — migration progressive

- Ancienne mémoire locale comme autorité → Soul comme référence canonique.
- Décision du LLM de chercher ou non un fait → récupération déterministe préalable.
- Valeurs et exceptions codées en dur → réglages explicites et documentés.
- Authentification navigateur actuelle → session/cookie sécurisé avant exposition
  hors LAN de confiance.
- Audio mobile LiveKit direct → routage Home Assistant Assist en fin de projet.

## DROP — à retirer après validation

- Branding Jarvis visible dans le lanceur, les pages et la documentation utilisateur.
- Prompts génériques trop longs pour le modèle local Holmes.
- Doublons de mémoire sans consommateur réel.
- Intégrations, skills et compatibilités héritées sans usage Holmes vérifié.
- Toute logique proactive où le LLM détecte lui-même un fait ou transporte un nom,
  une date, un chiffre ou un identifiant.

## Validé au 17 septembre 2026

- Soul branché sur le chat texte et le pipeline vocal LiveKit.
- Lecture contextuelle Home Assistant en lecture seule.
- Gmail et tous les calendriers Google visibles, dont Famille.
- Fenêtre Calendar bornée par `timeMin` et `timeMax`.
- Un calendrier Google inaccessible n'annule plus les autres.
- Routage Calendar limité aux intentions d'agenda, plus aux mots temporels seuls.
- Réponses directes Soul et Calendar persistées dans la session.
- Telegram autorisé explicitement en mode local.
- Appels internes et requêtes navigateur de même origine authentifiés.
- Interface Holmes accessible depuis Home Assistant sur le LAN.
- Mission Engine : critères de succès obligatoires, vérification en trois couches,
  gouvernance risque/permission/budget et retry borné présents et testés.
- Reprise de mission : les claims d'étapes sont désormais libérés à la fin du worker
  et nettoyés avant retry/reprise, y compris après interruption brutale.
- Initiatives : persistance multi-jours et restauration au redémarrage présentes ;
  l'ancien endpoint d'approbation délègue désormais au seul exécuteur gouverné.
- Un brouillon Gmail exige deux actions distinctes : préparation, puis confirmation
  explicite dans Mission Control. Aucun envoi direct depuis l'ancien dashboard.
- Validation : 873 tests réussis, 1 ignoré ; 2 tests de port non exécutables dans
  le bac à sable Codex car l'ouverture de sockets locaux y est interdite.

## Restant avant publication

1. Tester manuellement redémarrage, texte, voix Mac, Soul, HA et Google.
2. Remplacer l'injection du token API dans le HTML par une vraie session navigateur.
3. Authentifier explicitement les WebSockets avant toute exposition hors LAN fiable.
4. Choisir les modules hérités réellement inutilisés avant suppression.
5. Terminer le renommage externe Jarvis → Holmes sans casser le namespace Python.
6. Reporter l'audio mobile à la phase finale : HA Assist pour le micro et le routage,
   Holmes pour le raisonnement, puis TTS Home Assistant vers la bonne cible.
7. Ajouter une vraie récupération d'état des missions interrompues au démarrage :
   détecter `running`/`waiting_approval`, les placer en pause sûre, puis proposer la
   reprise dans Mission Control au lieu de dépendre d'un retry manuel.
8. Remplacer l'inférence textuelle des sources d'initiative par une provenance
   structurée issue des collecteurs, puis persister l'audit proactif sur disque.
9. Relier la fin d'une mission lancée par une initiative à son statut (`done` ou
   `failed`) afin d'éviter les initiatives durablement bloquées en `in_progress`.
