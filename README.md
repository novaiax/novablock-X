# NovaBlock

Bloqueur de contenu adulte pour Windows, avec un ami comme garde-fou.

Le déblocage exige un code de 25 caractères que **tu ne vois jamais**. Seul l'ami que tu as désigné le reçoit par email. Tu dois le lui demander.

---

## Téléchargement direct

Tous les fichiers ci-dessous se téléchargent en un clic, sans cloner le dépôt.

| Je veux… | Fichier | Télécharger |
|---|---|---|
| **Installer** | `NovaBlock.exe` | [Télécharger](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe) |
| **Mettre à jour** | `update.bat` | [Télécharger](https://github.com/novaiax/novablock-X/releases/latest/download/update.bat) |
| **Débloquer en urgence** | `EMERGENCY_RESET` | [.bat](https://github.com/novaiax/novablock-X/releases/latest/download/EMERGENCY_RESET.bat) - [.ps1](https://github.com/novaiax/novablock-X/releases/latest/download/EMERGENCY_RESET.ps1) |
| **Réactiver après** | `REACTIVATE` | [.bat](https://github.com/novaiax/novablock-X/releases/latest/download/REACTIVATE.bat) - [.ps1](https://github.com/novaiax/novablock-X/releases/latest/download/REACTIVATE.ps1) |
| **Réparer un navigateur** | `unstick_sockets` | [.bat](https://github.com/novaiax/novablock-X/releases/latest/download/unstick_sockets.bat) - [.ps1](https://github.com/novaiax/novablock-X/releases/latest/download/unstick_sockets.ps1) |
| **Débloquer un site légitime** | `whitelist_site` | [.bat](https://github.com/novaiax/novablock-X/releases/latest/download/whitelist_site.bat) - [.ps1](https://github.com/novaiax/novablock-X/releases/latest/download/whitelist_site.ps1) |
| **Mesurer le démarrage** | `MESURE_BOOT.ps1` | [Télécharger](https://github.com/novaiax/novablock-X/releases/latest/download/MESURE_BOOT.ps1) |

### Le plus simple : tout d'un coup

**[Télécharger NovaBlock-Outils.zip](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock-Outils.zip)** — tous les outils de secours, prêts à l'emploi.

> **Pourquoi le ZIP est recommandé :** chaque `.bat` appelle le `.ps1` du même nom **placé juste à côté de lui**. Si tu télécharges `EMERGENCY_RESET.bat` sans `EMERGENCY_RESET.ps1`, il ne fera rien. Le ZIP contient déjà les paires complètes.

Garde-le décompressé quelque part d'accessible — le jour où tu en auras besoin, tu n'auras peut-être plus internet.

Tous les `.bat` se lancent par **double-clic** et demandent les droits administrateur tout seuls.

---

## 1. Installer

1. Télécharge **[NovaBlock.exe](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe)**
2. Double-clique, accepte l'élévation administrateur
3. Suis le wizard :
   - Crée un compte gratuit sur [resend.com](https://resend.com) (3000 emails/mois)
   - Copie ta clé API depuis [resend.com/api-keys](https://resend.com/api-keys)
   - Saisis l'email de ton ami

C'est fini. L'icône bouclier apparaît dans la barre des tâches et le blocage est actif.

---

## 2. Mettre à jour

**Double-clic sur `update.bat`.**

Il télécharge le dernier `NovaBlock.exe` depuis GitHub et remplace l'ancien. Pas besoin de Python, ni d'être dans le dossier du projet : il retrouve seul l'endroit où NovaBlock est installé, en lisant le registre.

À la fin, il vérifie que tout fonctionne — résolution DNS, tâche planifiée, processus actif — et te dit quoi lancer s'il détecte un problème.

Ta configuration est conservée : elle est chiffrée dans `C:\ProgramData\NovaBlock\config.dat`.

> **`update_local.bat`** fait la même chose mais **recompile depuis le code source** de ton dossier, au lieu de télécharger. À utiliser seulement si tu as modifié le code toi-même. Il faut Python installé.

---

## 3. EMERGENCY RESET — quand plus rien ne marche

À utiliser si : plus d'internet, les navigateurs tournent en boucle, NovaBlock est coincé, `update.bat` échoue.

**Double-clic sur `EMERGENCY_RESET.bat`** (avec `EMERGENCY_RESET.ps1` dans le même dossier). Environ 10 secondes.

Si tu n'as rien sous la main, ouvre un **PowerShell administrateur** (Win+X puis Terminal administrateur) et colle :

```powershell
iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/EMERGENCY_RESET.ps1)
```

Ce que ça fait :

- Arrête NovaBlock et ses tâches planifiées (sans le code 25 caractères)
- Supprime les règles pare-feu `NovaBlock_DoH_*`
- Désactive le pare-feu Windows (temporairement)
- Remet le DNS en automatique sur toutes les interfaces
- Vide le bloc NovaBlock du fichier hosts
- Retire les politiques navigateur
- Ferme tous les navigateurs, vide les caches DNS et ARP

**Après ça, NovaBlock est complètement désactivé.**

### Réactiver ensuite

**Double-clic sur `REACTIVATE.bat`.** Il rallume le pare-feu, réactive les tâches planifiées et relance NovaBlock, qui réapplique tout.

Ou à distance :

```powershell
iex (irm https://raw.githubusercontent.com/novaiax/novablock-X/main/REACTIVATE.ps1)
```

---

## 4. Les autres outils

| Fichier | À quoi ça sert |
|---|---|
| `unstick_sockets.bat` | Répare les navigateurs qui ne chargent plus rien alors que la connexion marche |
| `whitelist_site.bat` | Débloque un site légitime mal classé comme adulte par le DNS familial |
| `MESURE_BOOT.ps1` | Mesure le temps entre le démarrage du PC et l'accès à internet |
| `build.bat` | Compile le `.exe` depuis les sources (nécessite Python) |

---

## Comment ça marche

**À l'installation**

- Un code de 25 caractères est généré au hasard
- Seule son empreinte argon2id est stockée sur le PC, chiffrée
- Le code en clair part par email chez ton ami
- Tu ne le vois jamais

**En permanence**

- **DNS** forcé sur Cloudflare Family (`1.1.1.3`) sur toutes les interfaces
- **Fichier hosts** : environ 76 800 domaines adultes redirigés vers `0.0.0.0`
- **Navigateurs** : DNS chiffré et navigation privée désactivés (Chrome, Edge, Firefox, Brave, Opera)
- **Pare-feu** : les serveurs DNS chiffrés connus sont bloqués, pour empêcher de contourner le filtre
- **Surveillance** : si le titre de la fenêtre active contient un mot-clé adulte, l'onglet est fermé
- **Tâche planifiée** : relance NovaBlock chaque minute s'il est tué

**Pour débloquer 24 heures**

Clique sur "Demander le code à mon ami". Un nouveau code est généré et envoyé, avec le contexte de ta demande. S'il te le donne, tu le saisis et le blocage tombe pour 24 heures.

**Rotation**

Tous les 7 jours le code est invalidé sans prévenir personne. La demande suivante en génère un nouveau.

**Pour désinstaller**

Bouton "Désinstaller", puis 7 jours d'attente obligatoires, puis le code. Annulable à tout moment.

---

## Bloquer d'autres sites

- **"Bloquer un site"** : immédiat, aucun code demandé. C'est fait exprès, se bloquer doit être facile.
- **"Retirer un site bloqué"** : code requis. Se débloquer doit être difficile.

---

## Ce que NovaBlock ne fait pas

C'est un outil d'auto-discipline, pas une forteresse. Quelqu'un de déterminé peut démarrer en mode sans échec, passer par une clé USB Linux, ou modifier le binaire.

Le but est de rendre le contournement assez pénible pour qu'un moment de faiblesse passe. Pas d'arrêter un attaquant motivé.

---

## Pour les développeurs

```bash
git clone https://github.com/novaiax/novablock-X.git
cd novablock-X
build.bat
```

Le `.exe` sort dans `dist\NovaBlock.exe`. Aucune clé API n'est nécessaire au build : elle est demandée au premier lancement.

Python 3.10+, Tkinter, pystray, pywin32, argon2-cffi, requests, psutil, PyInstaller.

---

## Licence

[MIT](LICENSE) par **Yann Wirtz**.

Liste de domaines : [StevenBlack/hosts](https://github.com/StevenBlack/hosts) - DNS familial : [Cloudflare 1.1.1.3](https://1.1.1.1/family/)
