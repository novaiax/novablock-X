# NovaBlock

NovaBlock est un bloqueur Windows de contenu adulte et de distractions, avec plusieurs couches de protection, une surveillance locale et des outils de récupération.

## Version actuelle

**v1.0.37**

La v1.0.37 se met à jour avec un seul fichier `update.bat` autonome. Elle ajoute un relais de relance local intégré à `NovaBlock.exe` : son processus porte un nom neutre, vérifie l'identité de l'application avant de la relancer dans la session utilisateur et ferme les fenêtres de navigateur reconnues pendant l'interruption. Le service système reste une seconde couche de récupération.

La configuration manquante ou illisible conserve le filtre actif si des traces d'installation existent. Les fichiers de données sont réservés aux administrateurs et à Windows. Les décisions de déblocage, de rotation du code et de désinstallation utilisent une heure HTTPS validée ; si elle est indisponible, ces actions restent verrouillées.

Les 17 sites personnels de la machine de référence sont présents dès la première installation. Lors d'une mise à jour, les entrées manquantes sont ajoutées une seule fois, en conservant les sites déjà configurés. Reddit n'est pas ajouté à cette liste ; son filtre NSFW distinct reste actif.

La publication exige la réussite des tests Windows et la vérification d'un redémarrage complet. Le workflow GitHub construit les artefacts, puis publie uniquement après un déclenchement manuel explicite depuis `main`.

Le service v1.0.36 avait relancé le processus principal en environ 1,1 à 1,3 seconde lors de trois événements journalisés sur le PC de référence. Le 30 septembre 2026, Windows Defender a ensuite mis son binaire en quarantaine ; son service s'est arrêté. Le temps observé pour le retour de l'icône était alors d'environ dix secondes. La v1.0.37 journalise séparément la détection de l'absence, le retour du processus et l'apparition de l'icône. Le seuil de deux secondes pour l'icône devra être confirmé après installation sur la machine concernée.

Le chemin rapide de récupération ne modifie pas le DNS, les cartes réseau, le service DNS Windows ni le fichier hosts. Ces mécanismes restent gérés par le cœur NovaBlock normal, pas par la couche de récupération v5.

## Incident de démarrage corrigé

Le diagnostic réel a montré qu'un ancien composant de démarrage lançait l'application complète dans la session Windows 0. Cette instance invisible prenait le mutex global avant l'ouverture de session de Yann : le processus apparaissait dans le Gestionnaire des tâches, mais aucune fenêtre, icône de zone de notification ni popup ne pouvait apparaître dans la session utilisateur. Une seconde instance interactive quittait alors immédiatement.

La correction agit à trois niveaux :

- l'ancien argument de service est reconnu et ne peut lancer qu'une réparation sans interface ;
- une garde interdit à l'interface graphique de démarrer en session 0 ;
- la couche v5 valide la tâche `NovaBlockApp` comme tâche interactive et nettoie ses seuls prédécesseurs connus depuis son contexte système.

La tâche `NovaBlockApp` reste le chemin normal de lancement au logon. Elle doit s'exécuter avec le jeton interactif de l'utilisateur, jamais sous `LocalSystem`.

## DNS familial et connexion Internet

Les adresses Quad9 `9.9.9.10` / `149.112.112.10` ont été retirées : elles ne constituent pas un filtre adulte/famille. NovaBlock utilise désormais uniquement des endpoints familiaux vérifiés, dans cet ordre :

1. Cloudflare Family ;
2. CleanBrowsing Family ;
3. OpenDNS FamilyShield, associé à Cloudflare Family pour IPv6.

IPv4 et IPv6 doivent tous deux rester filtrés. En cas de timeout Windows pendant la configuration, NovaBlock abandonne le changement en cours au lieu d'enchaîner les modifications réseau. Les contrôles de mise à jour vérifient ensuite à la fois la présence d'un DNS familial dual-stack et une connexion HTTPS bénigne.

## Téléchargement

La release GitHub contient :

| Fichier | Rôle |
| --- | --- |
| [`NovaBlock.exe`](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe) | application principale Windows |
| [`update.exe`](https://github.com/novaiax/novablock-X/releases/latest/download/update.exe) | composant de récupération téléchargé automatiquement par l'updater |
| [`update.bat`](https://github.com/novaiax/novablock-X/releases/latest/download/update.bat) | **seul fichier à télécharger pour une mise à jour complète** |
| [`NovaBlock-Outils.zip`](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock-Outils.zip) | outils de secours, mise à jour, réactivation et diagnostic |
| [`SHA256SUMS.txt`](https://github.com/novaiax/novablock-X/releases/latest/download/SHA256SUMS.txt) | empreintes SHA-256 des fichiers publiés |

Les binaires de release sont reconstruits par GitHub Actions à partir des sources du dépôt. Les empreintes officielles sont donc celles de `SHA256SUMS.txt` dans chaque release.

## Installation neuve

1. Lance `NovaBlock.exe` en administrateur et termine l'assistant. Il configure le blocage hosts, le DNS familial et les politiques navigateur, puis crée les **78 règles DoH de NovaBlock** et ses tâches de surveillance. Les autres règles du pare-feu Windows restent en place.
2. `NovaBlock.exe` contient le relais local. Pour ajouter le service système de récupération, télécharge et lance `update.bat`. Il demande l'UAC, télécharge le composant `update.exe` et contrôle son heartbeat. **`NovaBlock.exe` seul n'installe pas ce service.**

Sur une ancienne installation, lancer seulement `NovaBlock.exe` complète ou répare les règles requises, mais ne nettoie pas les milliers de doublons hérités. Ce nettoyage ciblé est effectué par `update.bat`.

## Mise à jour recommandée

1. Télécharge uniquement [`update.bat`](https://github.com/novaiax/novablock-X/releases/latest/download/update.bat) depuis la dernière release.
2. Double-clique dessus et accepte l'UAC. La fenêtre reste ouverte à la fin pour afficher le résultat et le chemin du journal.
3. Le script télécharge et vérifie `NovaBlock.exe` et `update.exe`.
4. Il remplace l'application principale en conservant la configuration dans `%ProgramData%\NovaBlock`.
5. Il vérifie les 78 règles DoH, retire uniquement les doublons anciens après sauvegarde, puis installe ou répare la couche de récupération v1.0.37.
6. Il relance NovaBlock et vérifie le heartbeat de l'application ainsi que celui du mécanisme de récupération.

Un update interrompu tente de restaurer l'installation précédente et demande son redémarrage. Il affiche séparément si la restauration et la demande de relance ont réussi ; leur réussite ne prouve pas encore que l'icône ou le service sont revenus. Le script n'arrête plus NovaBlock de force et ne modifie plus les ACL du fichier `hosts` : il demande un arrêt volontaire, attend de façon bornée et conserve une copie du cœur précédent. Une installation avec 78 règles valides ne subit aucun changement de pare-feu. Le nettoyage de règles anciennes demande un redémarrage Windows pour recharger la politique.

Le relais UAC est intégré à `update.bat` et conserve les chemins contenant des espaces. Le mode local écrit deux entrées SHA-256 distinctes, journalise son résultat final et laisse jusqu'à 20 secondes au watchdog pour appliquer le DNS familial avant de conclure à un échec. `update.exe` sait également reprendre une installation partielle dont le composant de récupération a déjà été créé puis verrouillé ; cette réparation reste strictement limitée au composant concerné et nettoie sa tâche ponctuelle.

## Architecture v1.0.34

La protection est volontairement séparée en deux niveaux.

### Socle v1.0.33 durci par v1.0.34

Le cœur Python garde les fonctions déjà stabilisées :

- blocage DNS/hosts et politiques navigateur ;
- surveillance des fenêtres et des sites configurés ;
- compagnon de récupération ;
- tâches planifiées et persistance ;
- interface, popup, code de désinstallation et configuration existante.

La v1.0.34 ajoute au cœur deux corrections bornées : la garde de session Windows 0 et l'exclusion des resolvers qui ne filtrent pas réellement le contenu adulte.

La fermeture explicite d'un onglet bloqué mémorise brièvement le handle ciblé après l'envoi réussi de `Ctrl+F4`. Cela évite un second popup pendant les quelques millisecondes où Chrome affiche encore l'ancien titre, tout en laissant les autres fenêtres et les échecs de fermeture immédiatement détectables.

### Couche de récupération v5

La v1.0.34 ajoute un composant autonome qui ne réimplémente pas les fonctions DNS/hosts du cœur.

Si l'application principale disparaît hors d'une maintenance officielle :

1. la disparition est détectée sur une cadence très courte ;
2. les navigateurs pris en charge sont fermés immédiatement via les API Windows ;
3. la protection réseau fail-closed et la demande de relance partent en parallèle ;
4. une courte suppression répétée des navigateurs couvre la transition ;
5. la protection réseau n'est libérée qu'après le retour stable de l'application principale.

Cette séparation évite de reproduire le problème des anciennes expérimentations v1.0.34 qui touchaient trop de composants réseau et pouvaient laisser la connexion lente à revenir.

## Outils de secours

`NovaBlock-Outils.zip` contient :

- `EMERGENCY_RESET.bat/.ps1` : outil de dernier recours avec UAC, plage horaire 19 h–6 h, défi manuel de 200 caractères et journal ;
- `REACTIVATE.bat/.ps1` : vérifie et rétablit les protections et le mécanisme de récupération ;
- `REPARE_INTERNET.ps1` : diagnostique le réseau et vérifie les 78 règles DoH sans supprimer leur jeu complet ;
- `unstick_sockets.bat/.ps1` : répare une pile réseau ou des navigateurs bloqués ;
- `whitelist_site.bat/.ps1` : traite un site légitime bloqué par erreur ;
- `MESURE_BOOT.ps1` : mesure le délai de disponibilité réseau après démarrage ;
- `update.bat` et `update.exe` : mise à jour et réparation ;
- `LISEZ-MOI.txt` : instructions correspondant aux fichiers de l'archive.

## Build et validation

La CI Windows effectue avant publication :

- tests Python `test_*.py` ;
- `compileall` du package Python ;
- compilation PyInstaller de `NovaBlock.exe` ;
- autotest runtime du binaire compilé ;
- `gofmt` et `go vet` de la couche de récupération ;
- compilation Windows x64 de `update.exe` ;
- tests statiques de cohérence release/outils ;
- génération des empreintes SHA-256 ;
- création de l'archive d'outils ;
- publication uniquement après un lancement manuel explicite du workflow depuis `main`, si toutes les étapes précédentes ont réussi.

## Développement local

Prérequis principaux : Python 3.12+, Go 1.22+ et Windows pour les tests runtime complets.

```bat
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
mkdir build
cd recovery_v134
go build -trimpath -ldflags="-s -w -H=windowsgui" -o ..\build\relay.exe .\cmd\relay
cd ..
python -m PyInstaller novablock.spec --clean --noconfirm --distpath dist-release
```

Pour la couche de récupération :

```bat
cd recovery_v134
gofmt -w cmd\recovery\main_windows.go
go vet ./...
go test ./...
go run github.com/tc-hib/go-winres@v0.3.3 simply --arch amd64 --out cmd\recovery\rsrc --manifest cli --admin --product-version 1.0.37.0 --file-version 1.0.37.0 --file-description "Application Continuity Runtime" --product-name "Continuity Runtime"
go build -trimpath -ldflags="-s -w" -o ..\dist-release\update.exe .\cmd\recovery
```

Pour installer localement les deux binaires construits, sans dépendre d'une release GitHub :

```bat
outils\update.bat --local "dist-release\NovaBlock.exe" "dist-release\update.exe"
```

Le mode local calcule et vérifie ses propres empreintes, utilise le même arrêt volontaire et exécute les mêmes contrôles finaux que le mode GitHub.

### Validation réelle sur chaque appareil

Après installation, contrôler les points suivants sur Windows :

- lancement manuel dans la session utilisateur avec fenêtre, zone de notification et popup ;
- blocage effectif, DNS familial IPv4/IPv6 et Internet bénin toujours disponible ;
- récupération automatique v5 sans modification du DNS dans le chemin rapide ;
- démarrage automatique après un redémarrage Windows complet, sans instance UI en session 0 ni ancien composant concurrent.

L'autotest du paquet et les tests simulés vérifient les chemins de code. UC Browser n'est pas installé sur le PC de référence et le portable concerné n'est pas accessible dans cette session : son fonctionnement réel, le retour de l'icône en moins de deux secondes et la résistance du service à Defender restent à mesurer après installation. Un résultat de test simulé ne vaut pas une validation sur cet appareil.

## Limites

NovaBlock ajoute de la friction et des couches de récupération. Un compte Windows disposant durablement de privilèges administrateur reste, par définition, capable de modifier son propre système avec suffisamment de volonté et de temps. L'objectif du projet est de supprimer les contournements rapides et impulsifs, pas de prétendre créer une protection matériellement inviolable.

## Licence

Voir [`LICENSE`](LICENSE).
