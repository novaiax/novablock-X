# NovaBlock

NovaBlock est un bloqueur de contenu adulte pour Windows avec un système d’accountability partner.

L’objectif est simple : rendre l’accès impulsif au contenu adulte suffisamment difficile pour que la décision ne repose pas uniquement sur la volonté du moment.

Le déblocage temporaire utilise un code de 25 caractères. Le code en clair n’est pas affiché à l’utilisateur : il est envoyé à l’ami de confiance configuré dans NovaBlock.

> Version actuelle : **v1.0.33**

---

## Téléchargement

| Besoin | Fichier | Lien |
|---|---|---|
| Installer NovaBlock | `NovaBlock.exe` | [Télécharger la dernière version](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock.exe) |
| Mettre NovaBlock à jour | `update.bat` | [Télécharger l’updater](https://github.com/novaiax/novablock-X/releases/latest/download/update.bat) |
| Outils de récupération | `NovaBlock-Outils.zip` | [Télécharger les outils](https://github.com/novaiax/novablock-X/releases/latest/download/NovaBlock-Outils.zip) |
| Vérifier le binaire | `SHA256SUMS.txt` | [Télécharger le checksum](https://github.com/novaiax/novablock-X/releases/latest/download/SHA256SUMS.txt) |

Les releases officielles sont compilées sur Windows par GitHub Actions, testées, puis soumises à un autotest du binaire avant publication.

---

## Installation

1. Télécharge `NovaBlock.exe` depuis la dernière release.
2. Lance l’exécutable et accepte l’élévation administrateur.
3. Suis l’assistant d’installation.
4. Configure :
   - ton prénom ;
   - le prénom de ton ami de confiance ;
   - son adresse email ;
   - une clé API Resend ;
   - l’adresse d’expédition utilisée par Resend.
5. NovaBlock génère le code initial et l’envoie à ton ami.

Une fois l’installation terminée, NovaBlock reste actif en arrière-plan et son icône apparaît dans la zone de notification Windows.

La configuration est stockée localement dans :

```text
C:\ProgramData\NovaBlock\config.dat
```

Les données sensibles de configuration sont chiffrées pour la machine locale.

---

## Deux systèmes distincts

NovaBlock sépare volontairement deux usages :

1. **le contenu adulte**, protégé par plusieurs couches système ;
2. **les sites personnels**, qui utilisent un popup après navigation réelle.

Cette séparation évite de transformer un simple site de distraction en problème DNS ou réseau.

---

## 1. Protection du contenu adulte

NovaBlock ne repose pas sur une seule technique.

### DNS

NovaBlock configure les interfaces réseau vers une liste de résolveurs approuvés et maintient cette configuration via son watchdog.

Plusieurs fournisseurs sont prévus dans le code afin de conserver une résolution DNS fonctionnelle lorsqu’un fournisseur n’est pas joignable.

### Domaines adultes connus

NovaBlock utilise une liste de domaines adultes issue de la blocklist `porn-only` de StevenBlack, complétée par une liste interne de domaines majeurs et de domaines explicitement surveillés.

Parmi les domaines couverts par les fallbacks internes figurent notamment les principaux sites pornographiques généralistes.

### SafeSearch

NovaBlock applique également des règles de recherche protégée pour les moteurs pris en charge, notamment Google et Bing.

### Navigateurs

Des politiques Windows sont appliquées aux navigateurs compatibles afin de limiter les voies de contournement :

- désactivation du DNS chiffré géré par le navigateur ;
- désactivation de la navigation privée lorsque le navigateur le permet ;
- règles spécifiques pour certains contenus NSFW, notamment Reddit sur les navigateurs Chromium.

Navigateurs principalement pris en charge :

- Chrome ;
- Edge ;
- Brave ;
- Firefox ;
- Opera ;
- Vivaldi.

### Pare-feu

NovaBlock ajoute des règles de pare-feu liées aux endpoints DNS chiffrés connus afin d’éviter qu’un navigateur contourne simplement la configuration DNS système.

### Monitor de contenu adulte

Un monitor observe la fenêtre active du navigateur.

Si le titre de la page contient un mot-clé adulte reconnu, NovaBlock peut afficher le popup plein écran même si le domaine lui-même n’était pas déjà connu.

Cette couche sert de filet de sécurité pour du contenu adulte hébergé ailleurs que sur les gros domaines classiques.

---

## 2. Sites personnels surveillés

Les sites personnels fonctionnent différemment depuis la v1.0.32.

Ils sont **popup-only**.

Cela signifie qu’un site ajouté dans `Sites personnels surveillés pour popup` n’est pas ajouté au DNS, au fichier hosts ou à la URLBlocklist du navigateur.

### Ce qui ne déclenche PAS le popup

NovaBlock ne déclenche rien simplement parce que :

- tu tapes l’adresse dans la barre d’adresse ;
- tu colles une URL ;
- le nom du site apparaît dans une page ;
- l’adresse apparaît dans un résultat de recherche ;
- le nom du site apparaît dans le titre d’un autre onglet ;
- un fragment banal du domaine apparaît dans du texte.

### Ce qui déclenche le popup

Le popup apparaît lorsque la navigation vers le site surveillé est réellement engagée.

NovaBlock lit l’adresse active du navigateur via Windows UI Automation et effectue un contrôle environ toutes les 100 ms lorsque cette détection est disponible.

Exemple :

```text
taper instagram.com
→ aucun popup

appuyer sur Entrée
→ navigation engagée
→ popup NovaBlock
```

### Fermer l’onglet déclencheur

Depuis la v1.0.33, le popup mémorise la fenêtre du navigateur qui a provoqué le déclenchement.

Quand tu cliques sur **« Fermer l’onglet »** :

1. NovaBlock masque le popup ;
2. redonne le focus à la fenêtre navigateur concernée ;
3. envoie un seul `Ctrl+F4` ;
4. ferme ensuite le popup.

Le but est de fermer **uniquement l’onglet qui a déclenché NovaBlock**.

NovaBlock ne tue plus tout le processus Chrome, Edge ou Firefox si cette fermeture échoue.

### Ajouter et retirer un site personnel

Depuis l’interface principale :

- **Ajouter un site popup** : aucun code requis ;
- **Retirer un site popup** : code de l’ami requis.

Il est possible de surveiller :

- un domaine complet ;
- une URL précise.

`movix.cash` est explicitement exclu de cette liste afin d’éviter un faux positif connu.

---

## Interface principale

L’interface actuelle utilise une taille fixe et compacte.

Elle affiche notamment :

- l’état du filtre ;
- le temps écoulé depuis l’installation ;
- les demandes de déblocage ;
- la prochaine rotation du code ;
- l’état éventuel du cooldown de désinstallation ;
- la liste exacte des sites personnels surveillés ;
- le nombre de règles popup actives.

La fenêtre principale reste à une taille stable : **620 × 700** avant adaptation DPI par Windows.

Elle ne grandit plus au fil des refresh.

---

## Déblocage temporaire de 24 heures

Le bouton **« Demander le code à mon ami »** déclenche une demande explicite.

NovaBlock :

1. génère un nouveau code ;
2. remplace l’ancien hash stocké ;
3. envoie le nouveau code à l’ami configuré ;
4. attend que l’utilisateur saisisse ce code.

Si le code est valide, le filtre peut être désactivé temporairement pendant 24 heures.

Un popup de blocage ordinaire **n’envoie pas automatiquement d’email**.

---

## Rotation du code

Le code a une durée de rotation configurée à 7 jours.

La rotation est silencieuse : elle ne provoque pas d’email à elle seule.

Lors de la prochaine demande explicite de déblocage, NovaBlock génère et envoie un code frais.

---

## Désinstallation

La désinstallation normale suit volontairement un processus lent :

1. lancer la demande depuis l’interface ;
2. attendre le cooldown de 7 jours ;
3. saisir le code détenu par l’ami de confiance ;
4. finaliser la désinstallation.

Le cooldown peut être annulé depuis l’interface avant son terme.

---

## Watchdog et relance automatique

NovaBlock utilise plusieurs mécanismes de persistance et de récupération.

Le système comprend notamment :

- une instance principale ;
- un processus compagnon ;
- une tâche planifiée watchdog ;
- une tâche interactive permettant de relancer l’interface dans la session utilisateur ;
- une heartbeat permettant de détecter une instance qui ne répond plus normalement.

Si le processus principal est fermé de manière inattendue, le système tente de relancer NovaBlock automatiquement.

Le but n’est pas de rendre le processus techniquement impossible à terminer, mais de rendre une fermeture ponctuelle non suffisante pour neutraliser durablement le blocage.

---

## Mise à jour

Télécharge puis lance :

```text
update.bat
```

L’updater :

- retrouve l’installation existante ;
- télécharge la dernière release ;
- demande proprement l’arrêt des processus NovaBlock ;
- vérifie qu’ils sont réellement arrêtés ;
- attend que Windows libère l’ancien `.exe` ;
- retente le remplacement si le fichier reste momentanément verrouillé ;
- relance NovaBlock ;
- vérifie l’état général après la mise à jour.

La configuration locale est conservée.

Depuis la v1.0.31, l’updater ne suppose plus que le processus est arrêté après un délai fixe : il vérifie réellement avant de remplacer le binaire.

---

## Outils de récupération

`NovaBlock-Outils.zip` contient les outils de diagnostic et de récupération du projet.

Ils sont destinés aux problèmes techniques réels : installation bloquée, réseau perturbé, diagnostic ou réparation.

Ils ne constituent pas le chemin normal de déblocage utilisateur ; le chemin prévu reste le code détenu par l’accountability partner et le processus intégré à NovaBlock.

---

## Emails

NovaBlock évite volontairement les notifications inutiles.

Des emails peuvent notamment être envoyés lors :

- de l’installation initiale ;
- d’une demande explicite de nouveau code ;
- du démarrage du processus de désinstallation lorsque cette action prévoit une notification.

La simple détection d’un site ou l’affichage d’un popup ne provoque pas automatiquement un nouvel email.

---

## Limites

NovaBlock est un outil d’auto-discipline Windows, pas une solution de sécurité matérielle ou un contrôle parental inviolable.

Un utilisateur disposant d’un contrôle total de la machine et déterminé à modifier profondément son environnement peut toujours finir par neutraliser un logiciel userland.

Le but du projet est différent : ajouter plusieurs couches de friction, rendre les contournements ordinaires pénibles et empêcher qu’une impulsion de quelques minutes suffise à désactiver le système.

---

## Développement

Cloner le dépôt :

```bash
git clone https://github.com/novaiax/novablock-X.git
cd novablock-X
```

Compiler sous Windows :

```bat
build.bat
```

Le projet utilise notamment :

- Python ;
- Tkinter ;
- pywin32 ;
- pywinauto ;
- psutil ;
- pystray ;
- Pillow ;
- argon2 ;
- requests ;
- PyInstaller.

Les releases officielles exécutent les tests `test_*.py`, compilent le véritable `NovaBlock.exe`, puis lancent un autotest du binaire compilé avant publication.

---

## Licence

NovaBlock est distribué sous licence [MIT](LICENSE).

La blocklist adulte externe utilisée par le projet provient de [StevenBlack/hosts](https://github.com/StevenBlack/hosts).
