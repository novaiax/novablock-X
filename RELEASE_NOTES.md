# NovaBlock v1.0.34 - récupération v5 et démarrage interactif

Cette candidate finalise l'architecture v5 validée en test réel et corrige le blocage du lancement Windows observé sur la machine de référence. Elle ne doit pas être publiée avant validation d'un redémarrage Windows complet.

## Ce qui change

- Ajout d'une couche de récupération Windows autonome, séparée du cœur Python.
- Détection très rapide de la disparition de l'application principale.
- Fermeture immédiate des navigateurs via API Windows pour supprimer la fenêtre interactive exploitable.
- Protection réseau fail-closed et relance de l'application lancées en parallèle.
- Courte suppression répétée des navigateurs pendant la transition.
- Libération de la protection réseau seulement après retour stable de l'application principale.
- Heartbeat dédié pour vérifier que le mécanisme de récupération est réellement actif après installation.
- Reconnaissance du mode de lancement historique comme mode strictement sans interface.
- Refus explicite de lancer l'UI en session Windows 0.
- Validation de `NovaBlockApp` comme tâche interactive avant installation de la récupération.
- Nettoyage, depuis le contexte système, des seuls composants de récupération prédécesseurs connus.
- Retrait des resolvers Quad9 non familiaux et sélection de DNS famille vérifiés sur IPv4 et IPv6.
- Reprise automatique d'une installation partielle déjà verrouillée, sans toucher au cœur actif ni au réseau.
- Suppression du double popup possible pendant la mise à jour tardive du titre Chrome après fermeture d'un onglet.

## Cause racine du démarrage invisible

Un ancien composant de démarrage lançait le cœur complet sous `LocalSystem`, en session Windows 0. Cette instance invisible prenait le mutex global ; l'instance lancée à l'ouverture de session détectait alors NovaBlock comme déjà actif et quittait. Le Gestionnaire des tâches montrait donc un processus, mais l'interface, la zone de notification et les popups étaient absents.

La v1.0.34 sépare désormais sans ambiguïté réparation headless et interface interactive. Même si un ancien lanceur tente encore d'utiliser l'argument historique, il ne peut plus créer une UI invisible ni verrouiller l'instance utilisateur.

## Test réel de référence

Sur la machine de test ayant validé la v5, une fermeture forcée de l'application principale a été suivie d'un retour observé en moins d'une seconde. Il n'était plus possible de profiter de l'intervalle pour commencer à naviguer ou lancer un téléchargement avant le retour de NovaBlock.

Ce chiffre est une observation sur cette machine, pas une garantie universelle de latence sur tous les PC Windows.

## Important : le chemin rapide ne touche plus au DNS

La récupération v5 ne réinitialise ni DNS, ni carte réseau, ni service DNS Windows, ni fichier hosts. Elle se limite au fail-closed temporaire, à la fermeture des navigateurs et à la relance.

Cela évite de réintroduire la régression des anciennes variantes v1.0.34 qui pouvaient laisser Internet indisponible plusieurs minutes.

Le cœur conserve la responsabilité DNS, mais n'accepte plus `9.9.9.10` / `149.112.112.10` comme DNS familiaux. Les fallbacks sont Cloudflare Family, CleanBrowsing Family puis OpenDNS FamilyShield avec un endpoint familial IPv6. La vérification finale exige aussi qu'une connexion HTTPS bénigne reste opérationnelle.

## Mise à jour et rollback

- `update.bat` télécharge maintenant l'application principale et la couche de récupération, vérifie les SHA-256, demande un arrêt volontaire, sauvegarde le cœur précédent, installe les deux, relance NovaBlock via sa tâche interactive et contrôle les heartbeats ainsi que le réseau.
- `update.bat --local` permet le même chemin transactionnel avec deux binaires construits localement, avant toute release GitHub.
- Le script ne force plus l'arrêt des processus et ne modifie plus les ACL du fichier `hosts`.
- Le relais UAC supporte les chemins avec espaces, le manifeste local contient deux lignes SHA-256 vérifiables et le contrôle final attend de façon bornée l'application du DNS familial.
- `update.exe` peut installer/réparer la couche v1.0.34 et son état réseau.
- `rollback_1.33.exe` retire uniquement la couche v1.0.34 et relance le socle v1.0.33 sans effacer la configuration.

## Outils de secours mis en cohérence

- `EMERGENCY_RESET` suspend proprement la couche de récupération avant son nettoyage de dernier recours.
- `REACTIVATE` réactive le pare-feu, les tâches, NovaBlock et la couche de récupération v1.0.34.
- `REPARE_INTERNET` sait désormais réparer un éventuel état fail-closed résiduel sans refaire le chemin réseau lourd.
- `LISEZ-MOI.txt` documente les nouveaux exécutables et leur rôle.

## Validation CI et publication

Les tests Python, l'autotest PyInstaller, les contrôles `gofmt`/`go vet`, la compilation Windows x64 des deux exécutables de récupération et les tests de cohérence release/outils doivent tous réussir.

Même après une CI verte, la publication n'est plus automatique sur `main`. Elle exige un déclenchement manuel explicite du workflow, après validation réelle du lancement, de l'UI, des popups, de la protection, de la récupération, d'Internet et du démarrage post-reboot.

## Validation locale de la candidate

La candidate réparée a passé sur la machine de référence :

- 81 tests Python, `compileall`, `gofmt`, `go vet` et `go test` ;
- l'autotest du binaire PyInstaller, y compris UI Automation, mutex, durcissement du processus et enfant indépendant ;
- deux mises à jour locales transactionnelles consécutives avec résultat `health=0` ;
- une fenêtre de diagnostic réellement visible en session interactive ;
- un test popup Chrome local avec une détection, un popup, un `Ctrl+F4` et le navigateur conservé ;
- hosts, DNS familial IPv4/IPv6, politiques navigateur et blocage DoH actifs, avec résolution DNS bénigne et HTTPS opérationnels ;
- heartbeat du mécanisme de récupération frais et absence de ses prédécesseurs.

Le redémarrage Windows complet reste le dernier verrou avant publication d'une release.

Les empreintes officielles des binaires publiés se trouvent dans `SHA256SUMS.txt` de la release.
