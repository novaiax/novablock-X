# NovaBlock v1.0.36 — mise à jour en un fichier et protections renforcées

Cette version conserve les protections de la v1.0.35 et simplifie l'installation : l'utilisateur télécharge uniquement `update.bat`. Ce fichier demande lui-même l'UAC, télécharge et vérifie `NovaBlock.exe` et le composant de récupération, puis laisse la fenêtre ouverte avec son résultat et le chemin du journal.

## Sites personnels et navigateurs

- Les 17 sites popup par défaut sont désormais ajoutés une seule fois aux installations existantes lors du redémarrage de NovaBlock après l'update. Les entrées personnelles déjà configurées sont conservées ; Reddit reste hors de cette liste.
- UC Browser est traité comme navigateur non vérifié : NovaBlock détecte ses processus connus et son emplacement d'installation, le ferme localement et affiche un popup explicatif tant que le filtre ne peut pas y être garanti. Le watchdog répète ce contrôle pendant le fonctionnement normal.

## DNS familial et pare-feu

- La vérification DNS lit les serveurs effectifs de **chaque interface réseau active**. Un ancien adaptateur configuré correctement ne peut plus masquer une interface Wi-Fi utilisant un DNS non familial.
- Un serveur secondaire non familial ou un IPv6 non familial est également détecté. Si le contrôle est indisponible, l'état est signalé comme inconnu et le prochain contrôle réessaie sans modifier aveuglément le réseau.
- L'updater vérifie les 78 règles DoH et leur nombre avant de relancer l'application. Il conserve le nettoyage ciblé des anciens doublons et indique quand un redémarrage Windows est nécessaire.

## Outils de secours

`NovaBlock-Outils.zip` conserve les outils de secours de la v1.0.35, dont `EMERGENCY_RESET` avec UAC, défi manuel de 200 caractères, plage horaire et journal. L'updater n'a plus besoin d'un script d'élévation séparé.

## Validation

Le workflow Windows exécute les tests Python, l'analyse des scripts PowerShell, les contrôles Go, la compilation et l'autotest du binaire empaqueté avant la publication manuelle depuis `main`.
