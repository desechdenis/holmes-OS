# Holmes OS — inventaire des contacts sortants

**Périmètre :** appels initiés par le dépôt Holmes OS à l'exécution, dans
l'interface web ou par un outil d'installation. L'état et l'exploitation des
systèmes Body sont documentés séparément ; leurs appels depuis Holmes figurent
bien ici.

Cet inventaire décrit le code présent, y compris les fonctions héritées ou
désactivées par défaut. Une clé absente empêche souvent l'appel concerné, mais
ne constitue pas un pare-feu. Il n'existe actuellement aucun kill switch réseau
global couvrant le serveur, le navigateur et les scripts.

## Modèles et voix

| Système visé | Lecture envoyée ou reçue | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| Anthropic | prompts, historique et réponses du modèle | consommation API | `LLM_PROVIDER=api`, `API_BACKEND=anthropic`, `ANTHROPIC_API_KEY` | `LLM_PROVIDER=local` et retrait de la clé |
| OpenAI | prompts/réponses ; audio si STT/TTS ; images si vision | consommation API et envoi de contenu | `API_BACKEND=openai`, `OPENAI_API_KEY`, ou fournisseur STT/TTS/vision correspondant | choisir un fournisseur local et retirer la clé |
| Mistral | prompts, historique et réponses | consommation API | `LLM_PROVIDER=api`, `API_BACKEND=mistral`, `MISTRAL_API_KEY` | `LLM_PROVIDER=local` et retrait de la clé |
| Gemini / Google AI | prompts/réponses et audio TTS | consommation API et envoi de contenu | `API_BACKEND=gemini`, `GEMINI_API_KEY`; TTS via `TTS_PROVIDER=gemini`, `GOOGLE_API_KEY` | choisir un fournisseur local et retirer les clés |
| Ollama | prompts, historique, réponses et appels d'outils | requêtes vers le serveur configuré | `LLM_PROVIDER=local`, `OLLAMA_BASE_URL` | arrêter Holmes ; Ollama est un moteur partagé et ne doit pas être arrêté par la procédure Holmes |
| Deepgram | flux audio STT et transcription | envoi audio | `STT_PROVIDER=deepgram`, `DEEPGRAM_API_KEY` | `STT_PROVIDER=whisper` et retrait de la clé |
| Google Speech | flux audio STT et transcription | envoi audio | `STT_PROVIDER=google`, `GOOGLE_APPLICATION_CREDENTIALS` | `STT_PROVIDER=whisper` et retrait du fichier de credentials |
| ElevenLabs | texte TTS, voix disponibles et audio généré | envoi de texte et consommation API | `TTS_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` | `TTS_PROVIDER=piper` et retrait de la clé |
| LiveKit | signalisation et flux audio temps réel | session WebRTC et publication audio | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | retirer ces trois valeurs et ne pas lancer le processus voix |

## Comptes et services Internet

| Système visé | Lecture | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| Google Calendar | calendriers et événements | création d'événements | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_TOKEN_PATH` | révoquer/supprimer le jeton et retirer les identifiants OAuth |
| Gmail | messages et fils | préparation puis envoi explicite d'un brouillon | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_GMAIL_TOKEN_PATH` | révoquer/supprimer le jeton Gmail et retirer les identifiants OAuth |
| Notion | page de tâches | aucune écriture dans l'adaptateur courant | `NOTION_TOKEN`, `NOTION_PAGE_ID` | retirer le jeton et l'identifiant |
| Spotify | lecture, appareils et état du lecteur | contrôle de lecture et OAuth | `MUSIC_PROVIDER=spotify`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_TOKEN_PATH` | choisir `MUSIC_PROVIDER=local`, révoquer/supprimer le jeton et retirer les identifiants |
| Deezer | catalogue, état OAuth | contrôle via l'API et OAuth | `MUSIC_PROVIDER=deezer`, `DEEZER_APP_ID`, `DEEZER_APP_SECRET`, `DEEZER_TOKEN_PATH` | choisir `MUSIC_PROVIDER=local`, révoquer/supprimer le jeton et retirer les identifiants |
| YouTube | chaîne, vidéos et statistiques | aucune écriture | `YOUTUBE_API_KEY`, `YOUTUBE_CHANNEL_ID` | retirer les deux valeurs |
| GitHub analytics | métadonnées du dépôt | aucune écriture dans le widget | `GITHUB_TOKEN`, `GITHUB_REPO` | retirer les deux valeurs et révoquer le jeton |
| Discord analytics | statistiques d'un serveur | aucune écriture dans le widget | `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID` | retirer les deux valeurs |
| wttr.in | météo d'une ville demandée à l'outil | aucune écriture | outil météo ; pas de clé ni de flag | arrêter Holmes ou retirer l'outil du registre |
| Open-Meteo | géocodage et prévisions proactives | aucune écriture | ville ou coordonnées configurées ; pas de clé | arrêter Holmes ; le mode local bloque le collecteur, mais les vues web restent indépendantes |
| Flux RSS publics | titres et résumés | aucune écriture externe | moteur proactif ; pas de clé ni de flag par collecteur | `PROACTIVE_LLM_ENABLED=false` coupe la boucle planifiée ; aucun flag RSS dédié |
| OpenSky et Nominatim | positions aériennes et géocodage | aucune écriture | routes Globe/carte invoquées ; pas de clé | ne pas ouvrir ces vues ou retirer les outils ; aucun flag dédié commun |
| Mapbox / MapTiler | cartes, styles et tuiles | télémétrie et consommation côté navigateur possibles | `MAPBOX_TOKEN`, `MAPTILER_KEY` | retirer les clés et ne pas ouvrir les vues cartographiques |
| AISStream | flux de positions publiques | abonnement au flux | `AISSTREAM_KEY` | retirer la clé |

## Systèmes Body appelés par Holmes

| Système visé | Lecture | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| Home Assistant | `GET /api/states`, puis filtrage local des états et attributs utiles | aucune : aucun appel de service et aucun verbe d'écriture n'est présent dans les deux adaptateurs HA | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | retirer le jeton ou vider sa valeur, puis redémarrer Holmes ; l'adaptateur n'est construit que si le jeton est présent |
| Soul MCP — lecture | initialisation MCP, `search_notes`, `read_note` pour le rappel et la liste de tâches | aucune sur ces chemins | `SOUL_MCP_URL`, `SOUL_PROJECT` | vider `SOUL_MCP_URL` puis redémarrer Holmes ; aucun client Soul n'est alors construit |
| Soul MCP — événements | aucune lecture métier | `SoulMemoryStore.append_event()` appelle `write_note` dans `holmes/events`, sans écrasement | même activation Soul | ce chemin n'a actuellement aucun appelant automatique dans `src/jarvis` : consolidation et collecteur HA ont été débranchés en phase 0. Couper Soul globalement avec `SOUL_MCP_URL`; conserver cette absence d'appelant comme invariant |
| Soul MCP — tâches | `read_note` sur la note de tâches | `SoulTaskStore._write_unlocked()` appelle `write_note` avec écrasement après création, modification, clôture ou suppression d'une tâche | même activation Soul | vider `SOUL_MCP_URL`; les écritures sont déclenchées explicitement par une commande de tâche, les routes tâches du dashboard, ou l'action explicite « initiative vers tâche » |

Le transport Soul utilise HTTP POST pour le protocole MCP, y compris pour les
outils de lecture ; le caractère lecture/écriture dépend du nom d'outil MCP.
Les deux seuls appels `write_note` de `providers/memory/soul.py` sont donc :

1. `append_event` : capacité d'écriture d'événement aujourd'hui dormante, sans
   déclencheur automatique dans le code de production ;
2. `_write_unlocked` : réécriture de la note canonique de tâches après une
   mutation demandée explicitement.

## Conversation Home Assistant vers Holmes

Le composant public
`integrations/home_assistant/custom_components/holmes_os/` inverse le sens de
l'appel : Home Assistant envoie le texte Assist à `POST /api/conversation` et
reçoit une réponse courte avec l'identifiant de session Holmes à réutiliser.

| Système visé | Lecture | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| API Holmes depuis Home Assistant | texte, langue et `conversation_id` Assist envoyés à Holmes ; réponse et nouvel identifiant lus par HA | ajout du dialogue à la session Holmes persistante ; aucune commande ni écriture Home Assistant | `API_AUTH_ENABLED=true` et `API_TOKEN` côté Holmes ; URL HTTPS, jeton, empreinte SHA-256 du certificat et agent de repli saisis dans l'interface HA | désactiver ou supprimer l'entrée `[HOLMES-OS]` dans HA, retirer Holmes du pipeline Assist, puis révoquer le jeton Holmes |

Le certificat auto-signé n'est jamais accepté sans vérification : le composant
épingle son empreinte SHA-256. Son délai de connexion est de 2 secondes et son
délai total de 20 secondes. Toute indisponibilité, expiration ou erreur
d'authentification déclenche l'agent HA de repli configuré, précédé de
« Holmes est indisponible ». Ce chemin utilise le profil vocal Holmes mais
n'ajoute aucun outil de pilotage domestique ; l'accès Holmes vers HA reste en
lecture seule comme décrit plus haut.

## Canaux de messagerie

| Système visé | Lecture | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| Telegram | messages entrants autorisés | réponses et notifications | `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID` | `TELEGRAM_ENABLED=false`, retrait/révocation du jeton |
| Discord | messages entrants autorisés | réponses et notifications | `DISCORD_ENABLED=true`, `DISCORD_BOT_TOKEN`, `DISCORD_OWNER_ID`; passerelle via `MESSAGING_GATEWAY_ENABLED` | `DISCORD_ENABLED=false`, `MESSAGING_GATEWAY_ENABLED=false`, retrait/révocation du jeton |
| Adaptateurs Slack, Signal et WhatsApp | code d'adaptation présent | aucun démarrage observé dans la composition actuelle | aucun couple complet de variables documenté | ne pas les enregistrer dans la passerelle ; supprimer toute configuration ajoutée localement |

`ALLOW_NETWORK_CHANNELS_IN_LOCAL_MODE=false` constitue une défense supplémentaire
quand `LLM_PROVIDER=local`; ce n'est pas un kill switch global.

## Matériel, outils et exécution générique

| Système visé | Lecture | Écriture ou effet | Activation `.env` | Coupure |
| --- | --- | --- | --- | --- |
| Imprimante compatible | état et télémétrie | commandes d'impression ou de contrôle | `PRINTER_IP`, `PRINTER_SERIAL`, `PRINTER_ACCESS_CODE` | retirer les trois valeurs |
| Serveur MCP Fusion | état et objets du projet | commandes de conception | `FUSION_ENABLED=true`, `FUSION_MCP_URL` | `FUSION_ENABLED=false` et retrait de l'URL |
| Navigateur HTTP générique | contenu de toute URL fournie | requête HTTP GET | outil `BrowserTool`, sans flag dédié | arrêter Holmes ou retirer l'outil du registre ; le mode local seul ne le bloque pas |
| Missions SSH/RPC/remote | fichiers, commandes et résultats | exécution distante | configuration de backend ; missions héritées via `MISSION_LEGACY_LOCAL_ENABLED` | conserver `MISSION_LEGACY_LOCAL_ENABLED=false`, supprimer les backends distants configurés |
| Docker | images, état des conteneurs | téléchargement d'image et exécution avec réseau éventuel | `DOCKER_ENABLED`, `DOCKER_NETWORK` | `DOCKER_ENABLED=false` et arrêt/suppression des conteneurs Holmes |
| CLI locale et sous-processus | sorties de commandes | exécution locale pouvant elle-même joindre le réseau | allowlist CLI ; `ALLOW_UNSANDBOXED_EXEC` | `ALLOW_UNSANDBOXED_EXEC=false`, réduire l'allowlist et arrêter Holmes |
| Skills et extensions | catalogues ou dépôts | téléchargement/installation de code | action manuelle ; `AUTO_INSTALL_WHITELISTED_ENABLED` pour l'automatique | `AUTO_INSTALL_WHITELISTED_ENABLED=false` et ne pas appeler les routes d'installation |
| Arduino/macropad | versions et archives d'outillage | téléchargement puis flash USB | action manuelle ; `ARDUINO_CLI` peut remplacer le binaire | ne pas appeler l'installation/le flash ; débrancher le périphérique si nécessaire |
| Webcam, écran et micro | images, écran et niveau sonore locaux | capture locale ; les images peuvent ensuite partir vers un fournisseur vision | `VISION_OBJECT_DETECTION`, `VISION_WEBCAM_INDEX`, `CLAP_DETECTION_ENABLED` ou appel manuel des outils | désactiver les deux flags, arrêter le worker vocal et retirer la permission système |
| Bundles et scripts d'installation | versions et archives publiques | téléchargement et installation locale | invocation manuelle des scripts | ne pas exécuter les scripts ; aucune activité au runtime normal |

## Dépendances chargées par le navigateur

Certaines pages chargent directement des polices, SDK ou modèles depuis Google
Fonts, jsDelivr, cdnjs, Spotify, Mapbox ou les dépôts de modèles MediaPipe. Ces
requêtes sont déclenchées par le navigateur dès l'ouverture des pages concernées
et ne sont pas toutes protégées par une variable `.env`. La coupure fiable est de
ne pas exposer ni ouvrir l'interface après l'arrêt de Holmes, ou de bloquer ces
domaines au niveau réseau. Leur auto-hébergement relève d'une phase ultérieure.

Les routes de diagnostic des fournisseurs déclenchent également des appels
externes à la demande, même si elles ne font pas partie du chemin conversationnel.
Elles n'ont pas d'interrupteur distinct : ne pas les appeler après neutralisation
des clés.

## Contrôle rapide

Pour neutraliser les sorties sans supprimer les données : arrêter d'abord Holmes,
laisser les modes legacy/proactif/installation automatique désactivés, désactiver
les canaux, puis révoquer les jetons OAuth et clés devenus inutiles. Le retrait
complet est décrit dans `scripts/holmes_uninstall.md`.
