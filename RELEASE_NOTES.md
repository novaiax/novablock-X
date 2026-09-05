## NovaBlock v1.0.29 : popup instantané pour les sites personnels

### Installation

Télécharger `update.bat` dans cette release puis l'exécuter en administrateur. Il remplace le `NovaBlock.exe` installé et conserve la configuration existante.

### Nouveau comportement

- Les domaines et URLs ajoutés manuellement dans NovaBlock sont maintenant lus directement par le monitor de fenêtres.
- Dès qu'un site personnel apparaît dans le titre du navigateur, NovaBlock déclenche le même popup plein écran que pour un contenu adulte.
- Le monitor vérifie la fenêtre active environ toutes les 100 ms. L'objectif est un popup perceptuellement instantané après l'apparition du titre dans le navigateur.
- Les nouveaux sites ajoutés sont rechargés depuis la configuration sans nécessiter de redémarrer NovaBlock.
- Les entrées existantes sont conservées à travers les mises à jour car elles restent stockées dans `config.dat`.

### Remarque technique

Le déclenchement repose sur le titre de la fenêtre du navigateur. Il est donc quasi instantané une fois que le navigateur a affiché un titre correspondant au site, mais ce n'est pas une interception réseau avant chargement.

### Inchangé

Aucun nouvel email n'est envoyé. Le système de code, la rotation, le cooldown de désinstallation, les filtres adultes, le watchdog et la relance automatique restent inchangés.

### Validation

La release est compilée sur Windows après exécution de tous les tests `test_*.py`, puis le véritable `NovaBlock.exe` passe l'autotest runtime avant publication.
