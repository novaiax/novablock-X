# NovaBlock v1.0.34 - récupération v5 et démarrage interactif

Cette version finalise l'architecture v5 validée en test réel et corrige le blocage du lancement Windows observé sur la machine de référence.

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

## Mise à jour et réparation

- `update.bat` télécharge maintenant l'application principale et la couche de récupération, vérifie les SHA-256, demande un arrêt volontaire, sauvegarde le cœur précédent, installe les deux, relance NovaBlock via sa tâche interactive et contrôle les heartbeats ainsi que le réseau.
- `update.bat --local` permet le même chemin transactionnel avec deux binaires construits localement, avant toute release GitHub.
- Le script ne force plus l'arrêt des processus et ne modifie plus les ACL du fichier `hosts`.
- Le relais UAC supporte les chemins avec espaces, le manifeste local contient deux lignes SHA-256 vérifiables et le contrôle final attend de façon bornée l'application du DNS familial.
- `update.exe` peut installer/réparer la couche v1.0.34 et son état réseau.

## Outils de secours mis en cohérence

- `REACTIVATE` réactive le pare-feu, les tâches, NovaBlock et la couche de récupération v1.0.34.
- `MESURE_BOOT` permet de mesurer le délai de disponibilité réseau après démarrage.
- `LISEZ-MOI.txt` décrit exactement les fichiers livrés dans l'archive d'outils.

## Validation CI et publication

Les tests Python, l'autotest PyInstaller, les contrôles `gofmt`/`go vet`, la compilation Windows x64 du composant de récupération et les tests de cohérence release/outils doivent tous réussir.

Même après une CI verte, la publication n'est plus automatique sur `main`. Elle exige un déclenchement manuel explicite du workflow, après validation réelle du lancement, de l'UI, des popups, de la protection, de la récupération, d'Internet et du démarrage post-reboot.

## Validation locale

La version réparée a passé sur la machine de référence :

- 75 tests Python, `compileall`, `gofmt`, `go vet` et `go test` ;
- l'autotest du binaire PyInstaller, y compris UI Automation, mutex, durcissement du processus et enfant indépendant ;
- deux mises à jour locales transactionnelles consécutives avec résultat `health=0` ;
- une fenêtre de diagnostic réellement visible en session interactive ;
- un test popup Chrome local avec une détection, un popup, un `Ctrl+F4` et le navigateur conservé ;
- hosts, DNS familial IPv4/IPv6, politiques navigateur et blocage DoH actifs, avec résolution DNS bénigne et HTTPS opérationnels ;
- heartbeat du mécanisme de récupération frais et absence de ses prédécesseurs.

Après un redémarrage Windows complet le 30 septembre 2026, le service de récupération était actif, son heartbeat était récent et l'application principale tournait dans la session utilisateur interactive. Le démarrage post-reboot a donc été vérifié sans fermer l'application pour provoquer une nouvelle récupération.

Les empreintes officielles des binaires publiés se trouvent dans `SHA256SUMS.txt` de la release.
