import logging
from datetime import datetime

import requests

log = logging.getLogger("novablock.mailer")

RESEND_URL = "https://api.resend.com/emails"


_LAST_ERROR: str = ""


def get_last_error() -> str:
    return _LAST_ERROR


def _send(api_key: str, from_email: str, to: str, subject: str, html: str) -> bool:
    global _LAST_ERROR
    _LAST_ERROR = ""
    if not api_key:
        _LAST_ERROR = "Pas de clé Resend configurée."
        log.error(_LAST_ERROR)
        return False
    try:
        r = requests.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_email, "to": [to], "subject": subject, "html": html},
            timeout=20,
        )
        if r.status_code >= 300:
            try:
                err = r.json().get("message", r.text)
            except Exception:
                err = r.text
            _LAST_ERROR = f"Resend [{r.status_code}] : {str(err)[:400]}"
            log.error(_LAST_ERROR)
            return False
        return True
    except Exception as e:
        _LAST_ERROR = f"Connexion Resend impossible : {e}"
        log.error(_LAST_ERROR)
        return False


def send_setup_email(api_key: str, from_email: str, friend_email: str,
                     friend_name: str, user_name: str, code: str,
                     machine_name: str = "") -> bool:
    label = f"{user_name}" + (f" — {machine_name}" if machine_name else "")
    subject = f"[{machine_name}] {user_name} a besoin de ton aide — code à conserver" if machine_name \
              else f"{user_name} a besoin de ton aide — code à conserver"
    machine_html = ""
    if machine_name:
        machine_html = (f'<p style="background:#dfe6e9;padding:10px;border-radius:6px;'
                        f'font-size:14px;margin:16px 0 0 0;color:#2d3436;">'
                        f'📍 <strong>Machine :</strong> {machine_name}<br>'
                        f'<small style="color:#636e72">'
                        f'(Si {user_name} a installé NovaBlock sur plusieurs machines, chaque '
                        f'machine a son propre code. Ce code-ci est pour <strong>{machine_name}</strong>.)'
                        f'</small></p>')
    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.6;">

      <h2 style="color: #d63031; margin-bottom: 4px;">Salut {friend_name} 👋</h2>
      <p style="color: #636e72; margin-top: 0;">Tu reçois cet email parce que <strong>{user_name}</strong> t'a choisi(e) comme personne de confiance.</p>
      {machine_html}

      <h3 style="color: #2d3436; margin-top: 28px;">📖 Ce qui se passe, en 30 secondes</h3>
      <p>{user_name} veut <strong>arrêter de regarder du contenu pornographique</strong>. Pour s'aider lui/elle-même, il/elle vient d'installer <strong>NovaBlock</strong>, un logiciel qui bloque ce type de contenu sur son ordinateur.</p>
      <p>Pour que ce soit vraiment efficace, le système est conçu pour que <strong>{user_name} ne puisse pas se débloquer tout seul(e)</strong>. C'est là que tu interviens.</p>

      <h3 style="color: #2d3436; margin-top: 28px;">🔑 Ton rôle</h3>
      <p>Tu reçois ci-dessous un <strong>code à 25 caractères</strong>. Ce code est <strong>le seul moyen</strong> de débloquer NovaBlock. <u>{user_name} ne le voit jamais</u> et n'a aucun moyen de le récupérer sur son ordinateur.</p>

      <div style="background: #fff3cd; border-left: 4px solid #d63031; padding: 18px; margin: 24px 0; border-radius: 6px;">
        <p style="margin: 0 0 8px 0; font-weight: bold; color: #d63031;">🔐 Code de déblocage (à conserver précieusement) :</p>
        <p style="font-family: 'Courier New', monospace; font-size: 22px; letter-spacing: 2px; margin: 8px 0 0 0; color: #2d3436; user-select: all; background: white; padding: 12px; border-radius: 4px; text-align: center;">{code}</p>
        <p style="margin: 12px 0 0 0; font-size: 13px; color: #636e72;">Ce code est valable 7 jours. Tu en recevras un nouveau automatiquement chaque semaine — l'ancien deviendra inutile.</p>
      </div>

      <h3 style="color: #2d3436; margin-top: 28px;">💌 Ce qui va se passer ensuite</h3>
      <p>Tu vas recevoir des emails de la part de NovaBlock dans plusieurs cas :</p>
      <ul>
        <li><strong>Chaque fois que {user_name} essaye de débloquer</strong> : tu recevras un mail "🚨 {user_name} demande à débloquer NovaBlock". Le mail te dira combien de fois il/elle a déjà demandé cette semaine.</li>
        <li><strong>Chaque semaine</strong> : un nouveau code t'est envoyé automatiquement (l'ancien devient invalide).</li>
        <li><strong>Si {user_name} lance la désinstallation</strong> : tu seras prévenu(e) (cooldown de 7 jours, puis code requis pour finaliser).</li>
      </ul>

      <h3 style="color: #2d3436; margin-top: 28px;">🤔 Comment réagir quand {user_name} te demande le code ?</h3>
      <p>C'est <strong>à toi de décider</strong>. Mais souviens-toi : si {user_name} te demande ce code, ça veut dire qu'il/elle essaye d'accéder à du contenu adulte <strong>maintenant</strong>, alors qu'il/elle a installé cette app à un moment de lucidité pour ne plus le faire.</p>
      <p>Tu peux :</p>
      <ul>
        <li><strong>Refuser</strong> (ignore simplement le mail). C'est probablement la bonne décision dans 95% des cas — c'est exactement pour ça que {user_name} t'a choisi(e).</li>
        <li><strong>Donner le code</strong> si tu juges que la situation le justifie. Le code donne 24h de déblocage, puis le filtre se réactive.</li>
      </ul>

      <h3 style="color: #2d3436; margin-top: 28px;">✅ Ce que je te demande maintenant</h3>
      <ol>
        <li><strong>Sauvegarde le code</strong> dans un endroit sûr (gestionnaire de mots de passe, note privée, capture d'écran archivée).</li>
        <li><strong>Confirme à {user_name}</strong> que tu as bien reçu le code (par message direct, pas en répondant à ce mail).</li>
        <li><strong>Ne le partage pas</strong> avec {user_name} sans réfléchir. C'est tout l'intérêt du système.</li>
      </ol>

      <div style="background: #f0f0f0; padding: 16px; margin-top: 28px; border-radius: 6px; font-size: 13px; color: #636e72;">
        <strong style="color: #2d3436;">Si tu ne veux pas être l'accountability partner de {user_name}</strong>, dis-le-lui directement pour qu'il/elle choisisse quelqu'un d'autre. Pas de pression, c'est une vraie responsabilité.
      </div>

      <p style="color: #636e72; font-size: 12px; margin-top: 32px; text-align: center;">
        Email automatique envoyé par NovaBlock, un outil open-source.<br>
        Ne réponds pas à ce mail, contacte {user_name} directement.
      </p>
    </div>
    """
    return _send(api_key, from_email, friend_email, subject, html)


def send_rotation_email(api_key: str, from_email: str, friend_email: str,
                        friend_name: str, user_name: str, code: str) -> bool:
    subject = f"NovaBlock — Nouveau code hebdomadaire pour {user_name}"
    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
      <h2 style="color: #d63031;">Nouveau code hebdomadaire</h2>
      <p>Salut {friend_name},</p>
      <p>Voici le <strong>nouveau code de déblocage</strong> de {user_name} pour les 7 prochains jours. L'ancien est désormais invalide.</p>
      <div style="background: #fff3cd; border-left: 4px solid #d63031; padding: 16px; margin: 24px 0; border-radius: 4px;">
        <p style="margin: 0 0 8px 0; font-weight: bold; color: #d63031;">⚠️ Nouveau code (valable 7 jours) :</p>
        <p style="font-family: monospace; font-size: 20px; letter-spacing: 2px; margin: 0; color: #2d3436; user-select: all;">{code}</p>
      </div>
      <p>Tu peux supprimer l'ancien code, il ne fonctionne plus.</p>
      <p style="color: #636e72; font-size: 13px; margin-top: 32px;">
        Date de rotation : {datetime.now().strftime('%d/%m/%Y à %H:%M')}.
      </p>
    </div>
    """
    return _send(api_key, from_email, friend_email, subject, html)


def send_unlock_request(api_key: str, from_email: str, friend_email: str,
                        friend_name: str, user_name: str,
                        count_week: int, count_total: int,
                        code: str = "",
                        context: str = "",
                        machine_name: str = "") -> bool:
    when = datetime.now().strftime("%d/%m/%Y à %H:%M")
    machine_tag = f"[{machine_name}] " if machine_name else ""
    subject = f"🚨 {machine_tag}{user_name} demande à débloquer NovaBlock"
    ctx_html = f"<p><strong>Contexte :</strong> {context}</p>" if context else ""
    machine_html = ""
    if machine_name:
        machine_html = (f'<p style="background:#dfe6e9;padding:8px;border-radius:4px;'
                        f'font-size:13px;margin:12px 0 0 0;color:#2d3436;">'
                        f'📍 Machine : <strong>{machine_name}</strong></p>')
    code_block = ""
    if code:
        code_block = f"""
      <div style="background: #fff3cd; border-left: 4px solid #d63031; padding: 18px; margin: 24px 0; border-radius: 6px;">
        <p style="margin: 0 0 8px 0; font-weight: bold; color: #d63031;">🔐 Code de déblocage actuel (valable 24h une fois utilisé) :</p>
        <p style="font-family: 'Courier New', monospace; font-size: 22px; letter-spacing: 2px; margin: 8px 0 0 0; color: #2d3436; user-select: all; background: white; padding: 12px; border-radius: 4px; text-align: center;">{code}</p>
        <p style="margin: 12px 0 0 0; font-size: 13px; color: #636e72;">Ce code remplace tous les codes précédents. Si tu décides de céder, donne-le à {user_name}.</p>
      </div>"""
    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.6;">
      <h2 style="color: #d63031;">🚨 Demande de déblocage</h2>
      <p>Salut {friend_name},</p>
      <p><strong>{user_name} essaie d'accéder à du contenu pornographique</strong> et vient de cliquer sur "Demander le code".</p>
      {machine_html}
      {ctx_html}
      <div style="background: #ffe9e9; border-left: 4px solid #d63031; padding: 16px; margin: 16px 0; border-radius: 6px;">
        <p style="margin: 4px 0;"><strong>Quand :</strong> {when}</p>
        <p style="margin: 4px 0;"><strong>Demandes cette semaine :</strong> {count_week}</p>
        <p style="margin: 4px 0;"><strong>Demandes au total :</strong> {count_total}</p>
      </div>
      {code_block}
      <p><strong>Si tu cèdes</strong> : donne-lui le code ci-dessus.<br>
      <strong>Si tu refuses</strong> (probablement la bonne décision) : ignore cet email. {user_name} reste bloqué(e), c'est ce qu'il/elle voulait quand il/elle a installé l'app à un moment de lucidité.</p>
      <p style="color: #636e72; font-size: 13px; margin-top: 32px;">
        Le code donne 24h de déblocage, puis le filtre se réactive automatiquement.
      </p>
    </div>
    """
    return _send(api_key, from_email, friend_email, subject, html)


def send_uninstall_request(api_key: str, from_email: str, friend_email: str,
                           friend_name: str, user_name: str,
                           machine_name: str = "") -> bool:
    machine_tag = f"[{machine_name}] " if machine_name else ""
    subject = f"⚠️ {machine_tag}{user_name} a lancé la désinstallation de NovaBlock (cooldown 7j)"
    machine_line = f"<p><strong>Machine :</strong> {machine_name}</p>" if machine_name else ""
    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
      <h2 style="color: #d63031;">⚠️ Désinstallation lancée</h2>
      <p>Salut {friend_name},</p>
      <p><strong>{user_name} a cliqué sur "Désinstaller NovaBlock"</strong>. Cooldown 7 jours en cours.</p>
      {machine_line}
      <p>Pendant 7 jours le filtre reste actif. À la fin {user_name} devra entrer le code que tu as pour finaliser.</p>
      <p>S'il/elle te recontacte rapidement pour le code, demande-toi pourquoi il/elle veut tout retirer plutôt qu'un déblocage 24h.</p>
      <p style="color: #636e72; font-size: 13px; margin-top: 32px;">
        Cooldown lancé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}.
      </p>
    </div>
    """
    return _send(api_key, from_email, friend_email, subject, html)
