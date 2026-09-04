## NovaBlock v1.0.28 : reprise après arrêt du processus

### Installation de la mise à jour

Télécharger `update.bat` dans les fichiers de cette release, puis l'exécuter en administrateur. Il télécharge le nouveau `NovaBlock.exe`, remplace l'exécutable installé et relance l'application. La configuration existante dans `C:\ProgramData\NovaBlock` est conservée. Il n'est pas nécessaire de refaire l'assistant d'installation.

### Correctifs

- Le watchdog SYSTEM ne se limite plus à réparer les filtres : lorsque le programme principal est absent, il demande sa relance via la tâche `NovaBlockApp`, dans la session interactive de l'utilisateur. La cadence de secours reste d'une minute, à laquelle s'ajoutent l'exécution du contrôle et le démarrage Windows. Ce n'est pas une garantie de délai maximal.
- La reprise fonctionne également lorsque les filtres sont déjà intacts ou qu'un déblocage temporaire autorisé est en cours.
- Chaque relance du compagnon ou du programme principal utilise un environnement PyInstaller indépendant. Les ressources temporaires de l'ancien processus ne sont plus partagées avec son remplaçant.
- Les signatures Win32 de manipulation des mutex utilisent des HANDLE complets, notamment sur Windows 64 bits. Les sondes referment leurs handles.
- La règle de refus de terminaison du processus est placée avant les règles d'autorisation existantes. Cela reste une protection discrétionnaire : un administrateur privilégié peut la contourner. La relance est donc nécessaire indépendamment de cette protection.
- Les tâches planifiées sont actualisées sans suppression préalable. Les échecs d'enregistrement sont journalisés.
- Les relances respectent les mises à jour et la désinstallation avec code. Les marqueurs de maintenance expirent pour éviter qu'une mise à jour interrompue ne suspende la reprise indéfiniment.

### Inchangé

Aucune modification des listes de blocage, des destinataires, des règles d'envoi de mails, du déblocage avec code ou du délai de désinstallation. Aucun nouvel email n'est déclenché par la récupération d'un processus arrêté.

### Vérification de cette release

Le workflow Windows doit réussir les tests de régression, compiler l'exécutable puis exécuter son autotest natif avant de publier les fichiers. L'autotest vérifie les dépendances Windows, les mutex, l'ordre des permissions et la création d'une instance compilée indépendante. Il n'installe pas le bloqueur et n'envoie aucun email.

Le scénario complet Gestionnaire des tâches / session interactive doit encore être confirmé sur le PC installé : les tests automatisés ne reproduisent pas sa configuration Windows exacte.

`SHA256SUMS.txt` contient l'empreinte du nouvel exécutable. Aucun identifiant Resend n'est incorporé à la version publique.
