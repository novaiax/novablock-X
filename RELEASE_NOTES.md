## NovaBlock v1.0.33 : fermer uniquement l'onglet qui a déclenché le popup

### Correctif principal

Le comportement du bouton du popup est maintenant strict :

- L'apparition du popup ne ferme plus aucun onglet automatiquement.
- NovaBlock mémorise la fenêtre navigateur (`HWND`) qui a déclenché le popup.
- Quand tu cliques sur `Fermer l'onglet`, NovaBlock masque le popup, redonne le focus à cette fenêtre précise et envoie exactement un `Ctrl+W`.
- Le popup se ferme ensuite.
- Le fallback qui pouvait tuer tout le processus Chrome/Edge/Firefox a été supprimé.
- En cas d'échec de fermeture de l'onglet, NovaBlock n'escalade jamais vers la fermeture complète du navigateur.

### Comportement attendu

`navigation vers un site surveillé → popup → clic Fermer l'onglet → seul l'onglet actif qui a déclenché NovaBlock est fermé → les autres onglets restent ouverts`.

### Conservé de v1.0.32

- Sites personnels = popup uniquement après navigation réellement engagée.
- Aucun popup pendant la saisie dans la barre d'adresse ou parce qu'une adresse apparaît dans une page.
- `movix.cash` exclu des sites personnels surveillés.
- Faux positif `pro` supprimé.
- Interface principale compacte et fixe.
- Sites adultes de base toujours protégés par DNS/hosts/policies + monitor en secours.
- Updater robuste contre les fichiers `NovaBlock.exe` temporairement verrouillés.

### Inchangé

Aucun nouvel email n'est envoyé. Le code, la rotation silencieuse, le cooldown de désinstallation, le watchdog et la relance automatique restent inchangés.

### Validation

La release est publiée uniquement après réussite de tous les tests `test_*.py`, compilation du vrai `NovaBlock.exe` sous Windows et autotest runtime du binaire compilé.
