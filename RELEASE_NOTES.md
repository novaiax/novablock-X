## NovaBlock v1.0.30 : détection URL réelle + liste visible des sites perso

### Installation

Télécharger `update.bat` dans cette release puis l'exécuter en administrateur. Il remplace le `NovaBlock.exe` installé et conserve la configuration existante dans `C:\ProgramData\NovaBlock`.

### Nouveau comportement

- Les sites personnels sont maintenant comparés à l'URL réelle de l'onglet actif via Windows UI Automation, au lieu de dépendre uniquement du titre de l'onglet.
- Le titre reste utilisé en fallback si l'URL n'est pas accessible.
- Le monitor vérifie la fenêtre active environ toutes les 100 ms pour déclencher le popup dès que possible.
- Les domaines personnalisés correspondent aussi à leurs sous-domaines.
- Les URLs précises correspondent à la page configurée et à ses descendants.
- La fenêtre principale NovaBlock affiche désormais une section `Sites personnels surveillés pour popup` avec la liste exacte lue depuis `config.dat`, le nombre d'entrées et l'état de la détection URL réelle.
- La liste se met à jour automatiquement après ajout/suppression, sans redémarrage.

### Pourquoi

La v1.0.29 essayait surtout de reconnaître les sites perso depuis le titre de l'onglet. Certains sites utilisent des titres qui ne contiennent jamais leur domaine, donc aucun popup n'apparaissait. La v1.0.30 corrige ce point en lisant l'adresse active elle-même.

### Inchangé

Aucun nouvel email n'est envoyé. Le système de code, le cooldown de désinstallation, les filtres adultes, le watchdog et la relance automatique restent inchangés.

### Validation

Tous les tests `test_*.py` doivent réussir sur Windows, puis le véritable `NovaBlock.exe` compilé passe l'autotest runtime avant publication.
