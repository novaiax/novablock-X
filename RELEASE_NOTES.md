# NovaBlock v1.0.35 — outils de secours et pare-feu DoH

Cette version conserve les corrections de récupération et de démarrage de la v1.0.34. Elle remet les outils de secours dans l'archive officielle et traite les règles DoH dupliquées sur les installations anciennes.

## Règles DoH pendant la mise à jour

- L'updater vérifie le jeu attendu de 78 règles avant de relancer NovaBlock.
- Une installation saine avec 78 règles actives reste inchangée.
- Si des doublons anciens sont présents, une sauvegarde du registre est créée, puis une règle de blocage valide est conservée pour chaque nom attendu. Le nettoyage s'arrête si une règle requise manque ou paraît invalide.
- Le rapport indique le nombre de règles avant et après. Un redémarrage Windows recharge la politique pare-feu après nettoyage.
- Pendant le fonctionnement normal, le watchdog contrôle désormais la présence des 78 règles et réinstalle immédiatement une règle manquante.

## Sites personnels à la première installation

Les 17 domaines personnels configurés sur la machine de référence sont maintenant ajoutés automatiquement lors d'une nouvelle installation. Reddit est exclu de cette liste popup par défaut ; son filtrage NSFW séparé reste en place. La liste personnelle déjà stockée sur les machines installées n'est pas remplacée.

## Outils de secours

- `EMERGENCY_RESET` conserve l'UAC, la vérification de l'heure de Paris, la plage bloquée de 19 h à 6 h et les journaux. Le défi manuel passe à 200 caractères ; la couche de récupération récente est prise en compte après réussite du défi.
- `REACTIVATE` rétablit le cœur, les tâches, les protections réseau et la récupération v1.0.35.
- `REPARE_INTERNET` vérifie la récupération et utilise le nettoyage ciblé des règles DoH.
- `unstick_sockets`, `whitelist_site`, `MESURE_BOOT`, `update.bat` et leur documentation sont inclus dans `NovaBlock-Outils.zip`.
- `SHA256SUMS.txt` contient les empreintes des deux exécutables, de l'updater et de l'archive d'outils.

## Publication

Le workflow Windows exécute les tests Python, les contrôles Go, la compilation et l'autotest du binaire empaqueté. La release est publiée seulement par un déclenchement manuel depuis `main` après réussite de ces étapes.
