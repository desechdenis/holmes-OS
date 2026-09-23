# Retrait réversible de Holmes OS

Cette procédure retire Holmes du poste qui l'exécute. Elle ne modifie aucun
système Body, aucune automatisation domestique et aucune mémoire canonique.
Les exemples emploient uniquement des chemins génériques et des valeurs factices.

## Principes

- Commencer par une extinction réversible ; ne supprimer qu'après le test de
  48 heures.
- Archiver les données locales avant toute suppression.
- Révoquer les accès auprès de leur fournisseur, pas seulement dans `.env`.
- Déplacer d'abord les fichiers dans une quarantaine datée plutôt que les effacer.
- Ne jamais utiliser une commande récursive si sa cible contient une variable vide.

## 1. Préparer la preuve et la sauvegarde

Depuis le dépôt local :

```bash
git status --short --branch
git rev-parse HEAD
git remote -v
```

Consigner le commit, la date, les intégrations volontairement actives et le nom
de l'archive de données. Créer l'archive hors du dépôt et, de préférence, hors de
la machine :

```bash
repo_dir="/chemin/factice/holmes-OS"
archive_dir="/volume/factice/sauvegardes"
archive_name="holmes-local-data-YYYYMMDD-HHMMSS.tar.gz"
tar -czf "${archive_dir}/${archive_name}" -C "${repo_dir}" memory_data data
shasum -a 256 "${archive_dir}/${archive_name}"
```

Ne poursuivre qu'après une vérification indépendante du checksum.

## 2. Éteindre Holmes

Arrêter le service supervisé, puis retirer son démarrage automatique :

```bash
cd "/chemin/factice/holmes-OS"
./jarvis service-stop
./jarvis service-uninstall
```

Arrêter séparément tout terminal, conteneur ou worker vocal lancé à la main. Ne
pas utiliser `pkill` à l'aveugle ; identifier d'abord les PID :

```bash
pgrep -af 'holmes|jarvis|livekit'
lsof -nP -iTCP -sTCP:LISTEN
```

Vérifier ensuite qu'aucun PID Holmes ne subsiste et qu'aucun service ne redémarre
après fermeture de session ou redémarrage de la machine.

### Retirer Holmes du pipeline Home Assistant

Dans l'interface Home Assistant, effectuer ces opérations sans modifier les
automatisations ni les moteurs partagés :

1. sélectionner l'agent de repli antérieur dans chaque pipeline Assist qui
   utilisait l'entité `[HOLMES-OS]` ;
2. désactiver puis supprimer l'entrée d'intégration `[HOLMES-OS] Holmes OS` ;
3. vérifier qu'aucune entité ou entrée portant `[HOLMES-OS]` ne subsiste ;
4. retirer le dossier `custom_components/holmes_os` copié dans la configuration
   HA, puis redémarrer HA selon la procédure normale de l'opérateur ;
5. révoquer le jeton API Holmes utilisé par cette entrée.

Ne pas supprimer l'agent conversationnel de repli, Home Assistant, son pipeline
Assist ou son moteur vocal : ils ont un cycle de vie indépendant de Holmes.

## 3. Neutraliser les redémarrages et sorties

Dans la configuration privée, conserver au minimum les valeurs suivantes pendant
la fenêtre d'observation :

```dotenv
PROACTIVE_LLM_ENABLED=false
MISSION_LEGACY_LOCAL_ENABLED=false
AUTO_INSTALL_WHITELISTED_ENABLED=false
ALLOW_UNSANDBOXED_EXEC=false
TELEGRAM_ENABLED=false
DISCORD_ENABLED=false
MESSAGING_GATEWAY_ENABLED=false
DOCKER_ENABLED=false
FUSION_ENABLED=false
VISION_OBJECT_DETECTION=false
CLAP_DETECTION_ENABLED=false
```

Retirer les clés, secrets, URL et fichiers de jetons des intégrations inutilisées.
Cette opération empêche une relance accidentelle, mais ne remplace pas l'arrêt des
processus : plusieurs outils publics et ressources web n'exigent aucune clé.

## 4. Révoquer les accès externes

À la fin du test de 48 heures, révoquer dans les consoles des fournisseurs :

- jetons OAuth et autorisations de compte ;
- clés API de modèles, voix, cartographie, médias et analytics ;
- jetons de bots et sessions de messagerie ;
- callbacks OAuth, webhooks et appareils autorisés ;
- accès de dépôt ou de téléchargement qui avaient été créés pour Holmes.

Supprimer ensuite les copies locales des jetons de la quarantaine finale. Ne
jamais afficher leur contenu dans un journal ou un ticket.

## 5. Retirer les artefacts locaux

Créer une quarantaine explicite, vérifier chaque cible, puis déplacer :

```bash
repo_dir="/chemin/factice/holmes-OS"
quarantine_dir="/chemin/factice/quarantaine-holmes-YYYYMMDD"
mkdir -p "${quarantine_dir}"
test -d "${repo_dir}/.git"
mv "${repo_dir}" "${quarantine_dir}/holmes-OS"
```

Rechercher séparément les éléments suivants et ne déplacer que ceux qui ont été
créés pour Holmes :

- fichier de service utilisateur et journaux associés ;
- environnement virtuel et caches de modèles ;
- certificats locaux, jetons OAuth et fichiers `.env` ;
- conteneurs, images et volumes portant explicitement le nom Holmes ;
- profils ou firmware de périphérique générés par Holmes ;
- données de session, initiatives, missions et journaux locaux déjà archivés.

Ne pas supprimer les logiciels partagés, moteurs locaux, runtimes ou périphériques
utilisés par d'autres applications.

## 6. Vérifier le retrait

Après un redémarrage :

```bash
pgrep -af 'holmes|jarvis|livekit'
lsof -nP -iTCP -sTCP:LISTEN
```

La vérification est réussie si :

- aucun processus ou service Holmes ne démarre ;
- aucun port n'est ouvert par Holmes ;
- aucun trafic sortant Holmes n'est observé ;
- aucun fournisseur ne reçoit de nouvel appel attribuable à Holmes ;
- les pipelines Assist répondent via leur agent indépendant et ne référencent
  plus d'entité `[HOLMES-OS]` ;
- le fonctionnement domestique et les données canoniques sont inchangés ;
- la sauvegarde est lisible et son checksum correspond.

Conserver la quarantaine pendant une durée décidée par l'opérateur. Sa suppression
définitive constitue une opération séparée et n'est pas couverte par cette procédure.

## Retour arrière

Avant suppression définitive, restaurer le dossier depuis la quarantaine, remettre
uniquement les secrets strictement nécessaires, puis réinstaller le service avec
la procédure normale. Une révocation fournisseur peut exiger de créer de nouveaux
identifiants ; ne jamais réutiliser un secret révoqué.
