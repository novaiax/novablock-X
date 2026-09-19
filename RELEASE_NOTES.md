## NovaBlock v1.0.35 : gardien SYSTEM isolé du réseau

### Pourquoi cette version existe

La v1.0.34 a tenté d'ajouter une couche anti-arrêt sous forme de service Windows LocalSystem, mais ce service exécutait également des vérifications et réapplications réseau fréquentes. Cette architecture a été abandonnée après l'observation d'une récupération Internet anormalement lente.

La v1.0.35 repart du code sain de la v1.0.33 et réintroduit uniquement la partie utile : un gardien de processus séparé.

### Nouveau : `NovaBlockGuardian`

Le nouveau service Windows :

- tourne sous LocalSystem ;
- surveille la présence du processus principal NovaBlock ;
- utilise la tâche interactive existante `NovaBlockApp` pour relancer l'interface si le processus disparaît ;
- demande au Service Control Manager de le redémarrer rapidement en cas de crash ;
- conserve les couches de reprise existantes de la v1.0.33.

### Isolation réseau obligatoire

Le gardien ne contient aucune logique de filtrage réseau.

Il ne doit appeler ni :

- la configuration DNS ;
- la réécriture du fichier hosts ;
- les politiques navigateur ;
- les règles de pare-feu / DoH.

Des tests de régression inspectent le module du service et font échouer la release si ces dépendances ou appels réapparaissent.

### Migration depuis la v1.0.34

La v1.0.34 utilisait le nom de service `NovaBlockService`.

La v1.0.35 :

- utilise un nouveau service nommé `NovaBlockGuardian` ;
- tente de supprimer l'ancien `NovaBlockService` pendant l'installation ;
- refait ce nettoyage depuis le watchdog planifié exécuté sous LocalSystem, ce qui permet de gérer une ancienne DACL trop restrictive pour un administrateur élevé ;
- déclenche immédiatement cette passe SYSTEM après une mise à jour réussie ;
- met également à jour EMERGENCY_RESET pour connaître les deux noms de service.

### Ce que cette version ne promet pas

NovaBlock reste un logiciel Windows userland. Un administrateur déterminé qui prend volontairement plusieurs mesures système peut encore finir par le neutraliser.

L'objectif testé de la v1.0.35 est plus précis : une fermeture ponctuelle du processus principal ne doit plus suffire à laisser NovaBlock durablement arrêté, et la couche chargée de la relance ne doit provoquer aucune reconfiguration réseau.

### Validation avant publication

La branche v1.0.35 doit réussir :

- tous les tests `test_*.py` ;
- les nouveaux tests d'isolation du gardien et de migration v1.0.34 ;
- la compilation PyInstaller sous Windows ;
- l'autotest du vrai `NovaBlock.exe` compilé.

Le comportement exact dans le Gestionnaire des tâches et le délai réel de reprise doivent encore être confirmés sur le PC installé avant de considérer la modification comme validée en conditions réelles.
