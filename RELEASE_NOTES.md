## NovaBlock v1.0.31 : updater robuste quand l'ancien exe reste verrouillé

### Correctif principal

Le précédent `update.bat` pouvait tenter de remplacer `NovaBlock.exe` alors qu'un ancien processus NovaBlock ou son image Windows détenait encore le fichier. Résultat : `Access is denied` à l'étape 5.

La v1.0.31 corrige ce chemin :

- Après création du `shutdown.sentinel`, l'updater vérifie réellement avec `tasklist` que tous les `NovaBlock.exe` ont disparu.
- Il attend jusqu'à 35 secondes au lieu de supposer que 6+2 secondes suffisent.
- Il retente `taskkill` / `Stop-Process` pour les anciennes versions ou processus bloqués.
- Même après disparition des processus, il laisse 2 secondes à Windows pour libérer l'image de l'exécutable.
- Le `move /Y` est ensuite retenté jusqu'à 12 fois si le fichier reste momentanément occupé.
- Si NovaBlock refuse toujours de s'arrêter, l'update s'annule proprement et réarme l'ancienne installation au lieu de tenter un remplacement voué à échouer.

### Fonctionnalités conservées de v1.0.30

- Détection des sites personnels depuis l'URL réelle de l'onglet actif via Windows UI Automation.
- Fallback par titre de l'onglet.
- Contrôle environ toutes les 100 ms.
- Section `Sites personnels surveillés pour popup` dans l'interface avec la liste exacte lue depuis `config.dat`.
- Aucun nouvel email.

### Installation

Télécharger `update.bat` de cette release puis l'exécuter en administrateur. La configuration existante dans `C:\ProgramData\NovaBlock` est conservée.
