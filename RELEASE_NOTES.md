# NovaBlock v1.0.37 — relance locale et audit de protection

La mise à jour se fait toujours avec un seul fichier à télécharger : `update.bat`. Les 17 sites popup par défaut, hors Reddit, et les 78 règles DoH requises sont conservés depuis la v1.0.36.

## Relance et incident Defender

- `NovaBlock.exe` embarque un petit relais local au nom de processus neutre. Il tourne dans la session utilisateur, reçoit la même protection de processus que le cœur, vérifie l'identité du processus principal, ferme les fenêtres de navigateurs reconnues pendant son absence et demande aussitôt sa relance. Le lancement direct évite le délai d'appel à la tâche planifiée dans le cas courant.
- Les métadonnées visibles du service de récupération portent aussi un intitulé neutre. L'updater vérifie toujours le service et son heartbeat.
- Le PC de référence a subi une mise en quarantaine de l'ancien binaire du service par Microsoft Defender. Les nouveaux candidats ont passé une analyse ciblée locale, mais une analyse statique ne prouve pas que Defender ne réagira pas à leur comportement après installation. Aucune exclusion antivirus générale n'est installée par cette release.
- Le journal distingue désormais l'absence du processus, son retour et l'apparition de l'icône. L'objectif de deux secondes pour l'icône doit être mesuré après installation sur l'appareil concerné.

## Résistance aux états dégradés

- Une configuration illisible ou disparue ne redevient pas une installation neuve si des traces du filtre sont présentes. Les changements sensibles sont alors refusés et le filtre reste actif.
- Le dossier de données et ses fichiers existants reçoivent des permissions réservées aux administrateurs et à Windows. La correction ne suit pas les liens qui sortent de ce dossier.
- Les tâches de démarrage sont contrôlées avant réparation ; un démarrage sain ne les réécrit plus systématiquement. Le contrôle se fait après le lancement de l'icône.
- Le remplacement du binaire de récupération conserve l'ancien fichier si Windows refuse le nouveau. Un échec de mise à jour indique séparément le résultat de la restauration et la demande de relance.
- Le déblocage temporaire, la validité du code et les sept jours de désinstallation s'appuient sur une heure HTTPS validée. Si cette heure devient indisponible, ces actions sensibles restent verrouillées.

## Navigateurs et popups

- UC Browser est couvert par ses processus connus, son chemin d'installation et le titre de sa fenêtre. Le relais local couvre aussi ses fenêtres pendant une interruption du cœur.
- La surveillance reconnaît davantage de navigateurs par leur barre d'adresse et maintient le popup lorsque la fermeture de l'onglet n'est pas confirmée. Le contrôle des politiques couvre chaque navigateur géré.

## Validation et limites

Les tests Python, Go, l'analyse PowerShell et l'autotest de l'EXE empaqueté sont les portes de publication du workflow Windows. Les tests UC Browser actuels simulent ses comportements : UC Browser n'est pas installé sur le PC de référence et le portable signalé n'est pas accessible ici. La vitesse réelle de retour de l'icône et la stabilité du service sous Defender restent à confirmer sur ces appareils.

La publication manuelle de la release se fait depuis `main` après la réussite de ces contrôles automatisés.

Cette release n'ajoute aucune modification DNS ou pare-feu. L'updater conserve les vérifications et réparations de la v1.0.36 ; les changements DNS/pare-feu issus de l'audit feront l'objet d'une décision séparée.
