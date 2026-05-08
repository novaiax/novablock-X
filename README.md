# NovaBlock

> Bloqueur de contenu adulte pour Windows avec **accountability partner**. Très chiant à contourner — c'est volontaire.

NovaBlock bloque l'accès aux sites pornographiques sur Windows en combinant DNS, fichier hosts, politiques navigateur, monitoring d'écran et pare-feu. Le seul moyen de débloquer est un code de 25 caractères que tu **ne vois jamais** : seul un ami que tu désignes le reçoit par email. Tu lui demandes le code, il décide de te le donner ou pas.

## Installation rapide (pour les utilisateurs)

### Option A — `.exe` pré-compilé (le plus simple)

1. Télécharge `NovaBlock.exe` depuis la [page Releases](https://github.com/novaiax/novablock-X/releases)
2. Double-clique → accepte l'élévation administrateur
3. Le wizard te guide en 4 étapes :
   - Crée un compte gratuit sur [resend.com](https://resend.com) (3000 emails/mois gratuits)
   - Récupère ta clé API : [resend.com/api-keys](https://resend.com/api-keys)
   - Optionnel : vérifie un domaine sur [resend.com/domains](https://resend.com/domains) pour pouvoir envoyer à n'importe quel email
   - Tu colles la clé + saisis l'email de ton ami → install terminée

C'est tout. L'app reste active dans le tray (icône bouclier rouge) et bloque automatiquement.

### Option B — Build depuis les sources

Pour les devs ou si tu ne fais pas confiance à un `.exe` aléatoire :

```bash
git clone https://github.com/novaiax/novablock-X.git
cd novablock-X
build.bat
```

Le `.exe` sort dans `dist\NovaBlock.exe`. Aucune clé Resend n'est nécessaire au build — elle se demande au premier lancement.

## Comment ça marche

**Au setup**
- Génère un code aléatoire de 25 caractères (ex : `XK7P9-2QR4M-8NLB3-7VFW6-CDH5T`)
- Hash le code en argon2id, stocke seulement le hash localement (chiffré DPAPI)
- Envoie le code en clair à ton ami par email
- Tu ne vois jamais le code

**Au quotidien**
- Hosts file : ~50 000 domaines adultes (StevenBlack list) + Yandex (search engine bypass) pointent vers `0.0.0.0`
- DNS : forcé sur Cloudflare Family (`1.1.1.3`) sur toutes les interfaces
- Politiques navigateur : DoH désactivé, mode privé désactivé (Chrome, Edge, Firefox, Brave, Opera)
- Pare-feu Windows : bloque les IPs de DoH connues (Cloudflare, Google, Quad9) sur ports 443/853
- Monitor d'écran : surveille le titre de la fenêtre active. Si un mot-clé adulte est détecté → popup plein écran + Ctrl+W envoyé au navigateur + kill du process si insistant
- Tâche planifiée Windows en SYSTEM : relance NovaBlock chaque minute si tué

**Pour débloquer 24h**
- Tu cliques "Demander le code à mon ami" dans le tray
- L'app génère un nouveau code, met à jour le hash, envoie le code à ton ami avec le détail de ta demande (compteur, contexte)
- Si ton ami décide de te le donner, tu l'entres dans l'app → 24h de débloquage
- Au bout de 24h, tout se réactive automatiquement

**Rotation hebdomadaire**
- Tous les 7 jours, le code en cours est invalidé silencieusement
- Pas de spam à ton ami
- Le prochain "Demander le code" génère et envoie un nouveau code

**Pour désinstaller**
- Bouton "Désinstaller" dans l'app
- Cooldown obligatoire de 7 jours
- Code requis à la fin
- Tu peux annuler le cooldown à tout moment

## Bonus : sites bloqués manuellement

Tu peux ajouter n'importe quel site au blocage (TikTok, Instagram, Twitter, YouTube…) :
- **Bouton "Bloquer un site (libre)"** : ajout immédiat, pas de code requis. C'est ton "moi du futur" qui te remercie.
- **Bouton "Retirer un site bloqué"** : code requis. Tu ne peux pas annuler tes décisions sans l'aide de ton ami.

## Limites honnêtes

NovaBlock est un outil d'auto-discipline, pas de niveau "kernel-rootkit". Un utilisateur déterminé peut :

- Booter en Safe Mode et désactiver la tâche planifiée
- Utiliser un live USB Linux pour modifier le fichier hosts
- Patcher le binaire

L'objectif est de rendre le contournement assez chiant pour qu'un moment de faiblesse abandonne. Pas de bloquer un attaquant motivé. Si tu veux du blindage kernel-level, il faut un pilote signé Microsoft (~250€/an de certificat WHQL).

## Mises à jour

Si tu as cloné le repo en local, double-clique `update.bat` (en admin). Le script :
1. Stop NovaBlock + scheduled task
2. Pull les dépendances
3. Rebuild le `.exe`
4. Relance la nouvelle version

Ta config (accountability partner, code, sites custom) est conservée — elle est chiffrée dans `C:\ProgramData\NovaBlock\config.dat`.

## Stack technique

- **Python 3.10+** + Tkinter (GUI built-in)
- **pystray + Pillow** (system tray icon)
- **pywin32** (DPAPI machine-scope encryption, Windows tasks, registry)
- **argon2-cffi** (hash du code, time_cost=3, memory=64MB)
- **requests** (Resend API)
- **psutil** (détection processus navigateur)
- **PyInstaller** (build `.exe`)

## Sécurité

- Code 25 caractères : 36²⁵ = 8.1×10³⁸ combinaisons possibles
- Argon2id avec time_cost=3, memory=64MB, parallelism=2 → un attaquant offline avec un GPU peut tester ~50 hashs/seconde max
- Stockage local : DPAPI scope MACHINE → chiffré avec une clé dérivée de la machine, accessible seulement par les processus de cette machine
- Email transactionnel via Resend (SPF + DKIM signés)

## Licence

[MIT](LICENSE) — fait par **Yann Wirtz**. Si tu améliores le projet, PR welcome.

## Crédits

- Liste de domaines adultes : [StevenBlack/hosts](https://github.com/StevenBlack/hosts)
- DNS familial : [Cloudflare 1.1.1.3](https://1.1.1.1/family/)
