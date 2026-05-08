"""Tamper detection: emails the accountability partner if NovaBlock detects
a bypass attempt. Triggers:
  - Hosts block was deleted between two watchdog ticks
  - DNS was reverted between two watchdog ticks
  - Browser policies were removed
  - Firewall DoH rules were removed
  - Scheduled task was deleted
  - User attempted --uninstall before cooldown elapsed
  - Multiple consecutive failed code verifications
"""
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from . import config

log = logging.getLogger("novablock.tamper")

RESEND_URL = "https://api.resend.com/emails"
COOLDOWN_FILE_KEY = "last_tamper_alert_ts"
ALERT_COOLDOWN_SEC = 3600  # don't spam — max 1 alert per hour per type


def _should_send(reason: str) -> bool:
    cfg = config.load()
    last_alerts = cfg.get("last_tamper_alerts", {}) or {}
    last = last_alerts.get(reason, 0)
    if time.time() - last < ALERT_COOLDOWN_SEC:
        return False
    last_alerts[reason] = int(time.time())
    cfg["last_tamper_alerts"] = last_alerts
    config.save(cfg)
    return True


def send_tamper_alert(reason: str, detail: str = "") -> bool:
    """Send an email to the accountability partner about a tampering attempt."""
    if not _should_send(reason):
        log.info("Tamper alert '%s' suppressed (cooldown)", reason)
        return False

    cfg = config.load()
    api_key = cfg.get("resend_api_key", "")
    from_email = cfg.get("from_email", "novablock@resend.dev")
    friend_email = cfg.get("friend_email", "")
    friend_name = cfg.get("friend_name", "ami")
    user_name = cfg.get("user_name", "l'utilisateur")
    machine_name = cfg.get("machine_name", "")

    if not api_key or not friend_email:
        log.warning("Tamper alert skipped: missing config")
        return False

    when = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    machine_tag = f"[{machine_name}] " if machine_name else ""
    subject = f"🚨 {machine_tag}{user_name} essaie de contourner NovaBlock"

    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.6;">
      <h2 style="color: #d63031;">🚨 Tentative de contournement détectée</h2>
      <p>Salut {friend_name},</p>
      <p><strong>{user_name} essaie de désactiver NovaBlock</strong> sans passer par la procédure officielle (demander le code, ou cooldown 7j de désinstallation).</p>

      <div style="background: #ffe9e9; border-left: 4px solid #d63031; padding: 16px; margin: 20px 0; border-radius: 6px;">
        <p style="margin: 4px 0;"><strong>Quand :</strong> {when}</p>
        <p style="margin: 4px 0;"><strong>Machine :</strong> {machine_name or 'inconnue'}</p>
        <p style="margin: 4px 0;"><strong>Type de tentative :</strong> {reason}</p>
        {f'<p style="margin: 4px 0;"><strong>Détail :</strong> {detail}</p>' if detail else ''}
      </div>

      <p>NovaBlock a <strong>bloqué la tentative</strong> et réappliqué automatiquement les protections.</p>

      <p>Si {user_name} te demande le code dans les minutes/heures qui viennent, ce mail t'aide à comprendre dans quel état mental il/elle est. Tu peux aussi lui rappeler que c'est exactement pour ça qu'il/elle t'a choisi(e).</p>

      <p style="color: #636e72; font-size: 12px; margin-top: 32px; text-align: center;">
        Email automatique. Ne réponds pas — contacte {user_name} directement.
      </p>
    </div>
    """

    try:
        r = requests.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_email, "to": [friend_email], "subject": subject, "html": html},
            timeout=20,
        )
        if r.status_code >= 300:
            log.error("Tamper alert email failed: %s", r.text[:200])
            return False
        log.warning("TAMPER ALERT sent to %s: %s", friend_email, reason)
        return True
    except Exception as e:
        log.error("Tamper alert exception: %s", e)
        return False


# Tamper reasons (used as keys for cooldown dedup)
HOSTS_REMOVED = "hosts_block_removed"
DNS_REVERTED = "dns_reverted"
POLICIES_REMOVED = "browser_policies_removed"
FIREWALL_REMOVED = "doh_firewall_removed"
TASK_DELETED = "scheduled_task_deleted"
UNINSTALL_BYPASS = "uninstall_before_cooldown"
WRONG_CODE_FLOOD = "repeated_wrong_codes"
