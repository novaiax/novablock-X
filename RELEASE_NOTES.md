## NovaBlock v1.0.32 : popup seulement après navigation réelle

### Comportement des sites personnels

Les sites ajoutés dans `Sites personnels surveillés pour popup` sont maintenant **popup uniquement**.

- Taper ou coller l'adresse dans la barre du navigateur ne déclenche rien.
- Voir le nom du site dans une page, un résultat Google, un message ou un titre ne déclenche rien.
- Le mot `pro` ou tout autre fragment provenant d'un domaine personnel ne peut plus devenir un faux mot-clé.
- Après validation de la navigation (Entrée / clic vers le site), NovaBlock lit l'adresse réellement engagée et peut déclencher le popup au prochain contrôle (~100 ms).
- Les sites personnels ne sont plus injectés dans `hosts` ni dans Chromium `URLBlocklist` : ils ne sont donc plus bloqués avant que le popup puisse apparaître.
- Les anciennes règles réseau personnalisées sont migrées et nettoyées une fois après mise à jour.

### movix.cash

`movix.cash` est explicitement retiré des sites personnels surveillés et ne peut plus être ajouté à cette liste. Les anciennes entrées `movix.cash` sont supprimées automatiquement lors de la migration.

Le filtre adulte général reste indépendant : un véritable mot-clé adulte dans le titre peut toujours déclencher NovaBlock.

### Interface

La fenêtre principale a été remise au propre :

- taille unique et fixe : 620 × 700 (adaptée au DPI par Windows) ;
- plus d'agrandissement au fil des refresh ;
- liste des sites personnels visible directement ;
- compteur d'entrées actif ;
- état clair : `Navigation réelle uniquement • saisie/texte ignorés • contrôle ~100 ms` ;
- ajout/suppression compactes, sans réappliquer DNS/hosts à chaque modification.

### Updater

Le correctif robuste de v1.0.31 est conservé : attente de l'arrêt réel de tous les processus NovaBlock, libération du fichier puis plusieurs tentatives de remplacement de l'exécutable en cas de verrou Windows temporaire.

### Inchangé

Aucun nouvel email n'est envoyé. Les règles d'envoi d'emails, le code, la rotation silencieuse, le cooldown de désinstallation, les filtres adultes, le watchdog et la relance automatique restent inchangés.

### Validation

La release est publiée uniquement après réussite de tous les tests `test_*.py`, compilation du vrai `NovaBlock.exe` sous Windows et autotest runtime du binaire compilé.
