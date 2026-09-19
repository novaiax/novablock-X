## NovaBlock v1.0.34 : service NT LocalSystem contre les kills Task Manager

### Contexte

Sous Windows, un administrateur porte par defaut le privilege `SeDebugPrivilege`. Ce privilege permet a Task Manager de contourner la DACL "deny PROCESS_TERMINATE" que NovaBlock applique sur son processus. En clair, la protection DACL existante suffit contre un user standard mais pas contre l administrateur qui ouvre son propre Task Manager.

### Ce qui change

NovaBlock installe maintenant un service NT sous compte LocalSystem, en plus des couches existantes.

- Task Manager > Processus n expose pas les services comme cible "Fin de tache" en un clic.
- Le Service Control Manager ne respecte pas `SeDebugPrivilege` pour un Stop de service.
- La DACL du service est verrouillee : services.msc ou `sc stop` renvoient Access denied tant que l administrateur n a pas explicitement pris possession du service.

### Boucle du service

- Reapplique le blocage sur hosts, DNS, browser policies et regles pare-feu DoH toutes les 5 secondes.
- Respawn de la fenetre principale via la tache planifiee interactive `NovaBlockApp`, jamais un Popen depuis la session 0.
- Cede la main quand `recovery.update_in_progress()` ou `recovery.shutdown_requested()` sont actifs, donc l updater et la desinstallation verifiee fonctionnent comme avant.

### Compatibilite

- Les couches existantes restent en place : DACL de processus, watchdog mutuel, taches planifiees, self-heal recovery.
- Aucune modification de `recovery.py`, `popup.py`, `custom_status.py`, `tab_close.py`, `companion.py`, `process_protect.py`, `monitor.py`, `browser_policies.py`, `blocker.py`, `config.py`.
- Nouveaux drapeaux CLI : `--service-run` (dispatch SCM), `--install-service`, `--uninstall-service`.

### Filet de securite

`EMERGENCY_RESET.bat` a ete etendu pour desserrer la DACL du service, l arreter et le supprimer avant la sequence habituelle. Si le service pose probleme, un reset ramene NovaBlock au comportement v1.0.33.

### Verification

Une fois v1.0.34 installee :
- ouvre Task Manager > Details
- clic droit sur `NovaBlock.exe` > Fin de tache
- resultat attendu : Access denied

Pour tester le service :
- `sc query NovaBlockService` renvoie RUNNING
- `sc stop NovaBlockService` renvoie Access denied par defaut

Pour desinstaller proprement :
- via l app : bouton "Desinstaller" apres cooldown 7 jours + code
- ou : `EMERGENCY_RESET.bat` pour rollback complet
