# NovaBlock

NovaBlock est un bloqueur Windows de contenu adulte et de distractions, avec plusieurs couches de protection, une surveillance locale et des outils de récupération.

## Version actuelle

**v1.0.34 (candidate de réparation, non publiée)**

La v1.0.34 part du cœur v1.0.33, ajoute la couche de récupération v5 validée en conditions réelles et corrige le démarrage interactif ainsi que la sélection du DNS familial.

La publication publique reste volontairement bloquée jusqu'à validation réelle d'un redémarrage Windows complet. Le workflow GitHub construit les artefacts sur les branches de réparation, mais une release exige désormais un déclenchement manuel explicite depuis `main`.

Lors du test réel ayant servi de référence, une fermeture forcée de l'application principale a été suivie d'un retour en moins d'une seconde. La v5 réduit aussi la fenêtre interactive entre la disparition de l'application et son retour en fermant immédiatement les navigateurs, puis en lançant en parallèle la protection réseau fail-closed et la relance.

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
| `NovaBlock.exe` | application principale Windows |
| `update.exe` | installe ou répare la couche de récupération v1.0.34 |
| `rollback_1.33.exe` | retire uniquement la couche v1.0.34 et remet en route le socle v1.0.33 |
| `update.bat` | mise à jour complète depuis la dernière release |
| `NovaBlock-Outils.zip` | outils d'urgence, réparation, réactivation et diagnostic |
| `SHA256SUMS.txt` | empreintes SHA-256 des exécutables publiés |

Les binaires de release sont reconstruits par GitHub Actions à partir des sources du dépôt. Les empreintes officielles sont donc celles de `SHA256SUMS.txt` dans chaque release.

## Mise à jour recommandée

1. Télécharger `update.bat` depuis la dernière release.
2. L'exécuter en administrateur.
3. Le script télécharge et vérifie `NovaBlock.exe` et `update.exe`.
4. Il remplace l'application principale en conservant la configuration dans `%ProgramData%\NovaBlock`.
5. Il installe ou répare la couche de récupération v1.0.34.
6. Il relance NovaBlock et vérifie le heartbeat de l'application ainsi que celui du mécanisme de récupération.

Un update interrompu est conçu pour échouer proprement et réarmer l'installation précédente plutôt que de laisser une mise à jour partielle. Le script n'arrête plus NovaBlock de force et ne modifie plus les ACL du fichier `hosts` : il demande un arrêt volontaire, attend de façon bornée, conserve une copie du cœur précédent et restaure cette copie si le swap n'aboutit pas.

Le relais UAC conserve les chemins contenant des espaces. Le mode local écrit deux entrées SHA-256 distinctes, journalise son résultat final et laisse jusqu'à 20 secondes au watchdog pour appliquer le DNS familial avant de conclure à un échec. `update.exe` sait également reprendre une installation partielle dont le composant de récupération a déjà été créé puis verrouillé ; cette réparation reste strictement limitée au composant concerné et nettoie sa tâche ponctuelle.

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

- `EMERGENCY_RESET.bat/.ps1` : procédure de dernier recours avec friction volontaire ;
- `REACTIVATE.bat/.ps1` : remet les protections et le mécanisme de récupération en état ;
- `REPARE_INTERNET.ps1` : diagnostique et répare les problèmes réseau connus et vérifie l'état fail-closed ;
- `MESURE_BOOT.ps1` : mesure le délai de disponibilité réseau après démarrage ;
- `unstick_sockets.bat/.ps1` : répare certains états réseau/navigateurs bloqués ;
- `whitelist_site.bat/.ps1` : ajoute une exception pour un site légitime mal classé ;
- `update.bat` et `update.exe` : mise à jour et réparation ;
- `rollback_1.33.exe` : retour contrôlé au socle v1.0.33.

`REACTIVATE` et `REPARE_INTERNET` sont compatibles avec la v1.0.34 : ils vérifient aussi la couche de récupération au lieu de supposer que seules les anciennes tâches planifiées existent.

## Retour au socle v1.0.33

`rollback_1.33.exe` retire la couche de récupération v1.0.34 sans remplacer la configuration ni désinstaller NovaBlock. Le cœur v1.0.33 reste le filet de secours et est relancé à la fin de l'opération.

## Build et validation

La CI Windows effectue avant publication :

- tests Python `test_*.py` ;
- `compileall` du package Python ;
- compilation PyInstaller de `NovaBlock.exe` ;
- autotest runtime du binaire compilé ;
- `gofmt` et `go vet` de la couche de récupération ;
- compilation Windows x64 de `update.exe` et `rollback_1.33.exe` ;
- tests statiques de cohérence release/outils ;
- génération des empreintes SHA-256 ;
- création de l'archive d'outils ;
- publication uniquement après un lancement manuel explicite du workflow depuis `main`, si toutes les étapes précédentes ont réussi.

## Développement local

Prérequis principaux : Python 3.12+, Go 1.22+ et Windows pour les tests runtime complets.

```bat
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
python -m PyInstaller novablock.spec --clean --noconfirm --distpath dist-release
```

Pour la couche de récupération :

```bat
cd recovery_v134
go run github.com/tc-hib/go-winres@v0.3.3 simply --arch amd64 --out cmd\recovery\rsrc --manifest cli --admin --product-version 1.0.34.0 --file-version 1.0.34.0 --file-description "NovaBlock recovery installer" --product-name "NovaBlock"
gofmt -w cmd\recovery\main_windows.go
go vet ./...
go build -trimpath -ldflags="-s -w" -o ..\dist-release\update.exe .\cmd\recovery
go build -trimpath -ldflags="-s -w -X main.defaultAction=rollback" -o ..\dist-release\rollback_1.33.exe .\cmd\recovery
```

Pour installer localement les deux binaires construits, sans dépendre d'une release GitHub :

```bat
outils\update.bat --local "dist-release\NovaBlock.exe" "dist-release\update.exe"
```

Le mode local calcule et vérifie ses propres empreintes, utilise le même arrêt volontaire et exécute les mêmes contrôles finaux que le mode GitHub.

### Validation réelle avant publication

La candidate n'est publiable qu'après validation de tous les points suivants sur Windows :

- lancement manuel dans la session utilisateur avec fenêtre, zone de notification et popup ;
- blocage effectif, DNS familial IPv4/IPv6 et Internet bénin toujours disponible ;
- récupération automatique v5 sans modification du DNS dans le chemin rapide ;
- démarrage automatique après un redémarrage Windows complet, sans instance UI en session 0 ni ancien composant concurrent.

## Limites

NovaBlock ajoute de la friction et des couches de récupération. Un compte Windows disposant durablement de privilèges administrateur reste, par définition, capable de modifier son propre système avec suffisamment de volonté et de temps. L'objectif du projet est de supprimer les contournements rapides et impulsifs, pas de prétendre créer une protection matériellement inviolable.

## Licence

Voir [`LICENSE`](LICENSE).
