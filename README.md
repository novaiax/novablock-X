# NovaBlock

Bloqueur de contenu adulte pour Windows, avec un ami comme garde-fou.

Le déblocage exige un code de 25 caractères que **tu ne vois jamais**. Seul l'ami que tu as désigné le reçoit par email. Tu dois le lui demander.

---

## Quel fichier pour quoi

| Je veux… | Fichier | Où |
|---|---|---|
| **Installer** | `NovaBlock.exe` | [Page Releases](https://github.com/novaiax/novablock-X/releases/latest) |
| **Mettre à jour** | `update.bat` | Racine du dossier du projet |
| **Tout débloquer en urgence** | `EMERGENCY_RESET.bat` | Racine du dossier du projet |
| **Réactiver après une urgence** | `REACTIVATE.bat` | Racine du dossier du projet |
| **Réparer un navigateur bloqué** | `unstick_sockets.bat` | Racine du dossier du projet |

Tous ces `.bat` se lancent par **double-clic**. Ils demandent les droits administrateur tout seuls.

---

## 1. Installer

1. Va sur la [page Releases](https://github.com/novaiax/novablock-X/releases/latest)
2. Télécharge **`NovaBlock.exe`**
3. Double-clique, accepte l'élévation administrateur
4. Suis le wizard :
   - Crée un compte gratuit sur [resend.com](https://resend.com) (3000 emails/mois)
   - Copie ta clé API depuis [resend.com/api-keys](https://resend.com/api-keys)
   - Saisis l'email de ton ami

C'est fini. L'icône bouclier apparaît dans la barre des tâches et le blocage est actif.

---

## 2. Mettre à jour

**Double-clic sur `update.bat`.**

Il télécharge le dernier `NovaBlock.exe` depuis GitHub et remplace l'ancien. Pas besoin de Python.

Ta configuration est conservée : elle est chiffrée dans `C:\ProgramData\NovaBlock\config.dat`.

> **`update_local.bat`** fait la même chose mais **recompile depuis le code source** de ton dossier, au lieu de télécharger. À utiliser seulement si tu as modifié le code toi-même. Il faut Python installé.

---

## 3. EMERGENCY RESET — quand plus rien ne marche

À utiliser si : plus d'internet, les navigateurs tournent en boucle, NovaBlock est coincé, `update.bat` échoue.

**Double-clic sur `EMERGENCY_RESET.bat`.** Environ 10 secondes.

Si tu n'as pas le dossier sous la main, ouvre un **PowerShell administrateur** (Win+X → Terminal administrateur) et colle :

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

## 4. Les autres scripts

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
- Seul son empreinte argon2id est stockée sur le PC, chiffrée
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

Clique sur « Demander le code à mon ami ». Un nouveau code est généré et envoyé, avec le contexte de ta demande. S'il te le donne, tu le saisis et le blocage tombe pour 24 heures.

**Rotation**

Tous les 7 jours le code est invalidé sans prévenir personne. La demande suivante en génère un nouveau.

**Pour désinstaller**

Bouton « Désinstaller », puis 7 jours d'attente obligatoires, puis le code. Annulable à tout moment.

---

## Bloquer d'autres sites

- **« Bloquer un site »** : immédiat, aucun code demandé. C'est fait exprès — se bloquer doit être facile.
- **« Retirer un site bloqué »** : code requis. Se débloquer doit être difficile.

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

[MIT](LICENSE) — par **Yann Wirtz**.

Liste de domaines : [StevenBlack/hosts](https://github.com/StevenBlack/hosts) · DNS familial : [Cloudflare 1.1.1.3](https://1.1.1.1/family/)
