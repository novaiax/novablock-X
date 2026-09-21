# NovaBlock v1.0.34 - récupération v5

Cette release finalise sur GitHub l'architecture v5 validée en test réel, tout en gardant le cœur applicatif v1.0.33 comme socle sain.

## Ce qui change

- Ajout d'une couche de récupération Windows autonome, séparée du cœur Python.
- Détection très rapide de la disparition de l'application principale.
- Fermeture immédiate des navigateurs via API Windows pour supprimer la fenêtre interactive exploitable.
- Protection réseau fail-closed et relance de l'application lancées en parallèle.
- Courte suppression répétée des navigateurs pendant la transition.
- Libération de la protection réseau seulement après retour stable de l'application principale.
- Heartbeat dédié pour vérifier que le mécanisme de récupération est réellement actif après installation.
- Nettoyage des anciennes expérimentations v1.0.34 lors de l'installation/réparation.

## Test réel de référence

Sur la machine de test ayant validé la v5, une fermeture forcée de l'application principale a été suivie d'un retour observé en moins d'une seconde. Il n'était plus possible de profiter de l'intervalle pour commencer à naviguer ou lancer un téléchargement avant le retour de NovaBlock.

Ce chiffre est une observation sur cette machine, pas une garantie universelle de latence sur tous les PC Windows.

## Important : le chemin rapide ne touche plus au DNS

La récupération v5 ne réinitialise ni DNS, ni carte réseau, ni service DNS Windows, ni fichier hosts. Elle se limite au fail-closed temporaire, à la fermeture des navigateurs et à la relance.

Cela évite de réintroduire la régression des anciennes variantes v1.0.34 qui pouvaient laisser Internet indisponible plusieurs minutes.

## Mise à jour et rollback

- `update.bat` télécharge maintenant l'application principale et la couche de récupération, vérifie les SHA-256, installe les deux, relance NovaBlock et contrôle les heartbeats.
- `update.exe` peut installer/réparer la couche v1.0.34 et son état réseau.
- `rollback_1.33.exe` retire uniquement la couche v1.0.34 et relance le socle v1.0.33 sans effacer la configuration.

## Outils de secours mis en cohérence

- `EMERGENCY_RESET` suspend proprement la couche de récupération avant son nettoyage de dernier recours.
- `REACTIVATE` réactive le pare-feu, les tâches, NovaBlock et la couche de récupération v1.0.34.
- `REPARE_INTERNET` sait désormais réparer un éventuel état fail-closed résiduel sans refaire le chemin réseau lourd.
- `LISEZ-MOI.txt` documente les nouveaux exécutables et leur rôle.

## Validation CI

La release n'est publiée que si les tests Python, l'autotest PyInstaller, les contrôles `gofmt`/`go vet`, la compilation Windows x64 des deux exécutables de récupération et les tests de cohérence release/outils réussissent.

Les empreintes officielles des binaires publiés se trouvent dans `SHA256SUMS.txt` de la release.
