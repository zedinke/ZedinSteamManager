"""
Email szolgáltatás
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import Request
from app.config import settings
from app.services.smtp_config import get_smtp_settings
from pathlib import Path

async def send_email(to: str, subject: str, body: str, is_html: bool = True, domain: str = None) -> bool:
    """Email küldése"""
    try:
        message = MIMEMultipart("alternative")
        message["From"] = f"{settings.email_from_name} <{settings.email_from}>"
        message["To"] = to
        message["Subject"] = subject
        
        if is_html:
            message.attach(MIMEText(body, "html", "utf-8"))
        else:
            message.attach(MIMEText(body, "plain", "utf-8"))
        
        # SMTP beállítások prioritása:
        # 1. config/app.py (settings.smtp_*) - ha be van állítva
        # 2. Exim konfiguráció
        # 3. Alapértelmezett (localhost)
        
        # Először nézzük meg, hogy van-e beállítva a config/app.py-ban
        use_config_smtp = (
            settings.smtp_host and 
            settings.smtp_host != "localhost" and 
            settings.smtp_user
        )
        
        if use_config_smtp:
            # config/app.py-ból használjuk
            smtp_host = settings.smtp_host
            smtp_port = settings.smtp_port
            smtp_user = settings.smtp_user
            smtp_pass = settings.smtp_pass
        else:
            # Próbáljuk az Exim konfigurációt
            smtp_config = get_smtp_settings(domain)
            smtp_host = smtp_config.get('host') or settings.smtp_host
            smtp_port = smtp_config.get('port') or settings.smtp_port
            smtp_user = smtp_config.get('user') or settings.smtp_user
            smtp_pass = smtp_config.get('pass') or settings.smtp_pass
        
        # TLS beállítások
        # Port 465 = SSL/TLS (use_tls=True)
        # Port 587 = STARTTLS (start_tls=True)
        # Port 25 = általában nincs TLS
        use_tls_param = (smtp_port == 465)
        start_tls_param = (smtp_port == 587)
        
        # Debug információk
        print(f"[EMAIL] Küldés: {to}")
        print(f"[EMAIL] SMTP Host: {smtp_host}:{smtp_port}")
        print(f"[EMAIL] SMTP User: {smtp_user if smtp_user else '(nincs)'}")
        print(f"[EMAIL] TLS: {use_tls_param}, STARTTLS: {start_tls_param}")
        print(f"[EMAIL] Config forrás: {'config/app.py' if use_config_smtp else 'Exim vagy alapértelmezett'}")
        
        # Ha nincs SMTP host vagy user, akkor nem küldünk emailt
        if not smtp_host or smtp_host == "localhost":
            print(f"[EMAIL] HIBA: SMTP host nincs beállítva vagy localhost. Email nem küldhető.")
            print(f"[EMAIL] Javaslat: Állítsd be a config/app.py fájlban az SMTP beállításokat!")
            return False
        
        if not smtp_user:
            print(f"[EMAIL] HIBA: SMTP user nincs beállítva. Email nem küldhető.")
            print(f"[EMAIL] Javaslat: Állítsd be a config/app.py fájlban az SMTP user-t!")
            return False
        
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user if smtp_user else None,
            password=smtp_pass if smtp_pass else None,
            use_tls=use_tls_param,
            start_tls=start_tls_param,
            timeout=10
        )
        
        print(f"[EMAIL] Sikeresen elküldve: {to}")
        return True
    except Exception as e:
        import traceback
        print(f"[EMAIL] Hiba küldéskor: {e}")
        print(f"[EMAIL] Traceback: {traceback.format_exc()}")
        return False

def get_email_template(template_name: str, **kwargs) -> str:
    """Email template betöltése"""
    template_dir = Path(__file__).parent.parent.parent / "templates" / "emails"
    template_file = template_dir / f"{template_name}.html"
    
    if template_file.exists():
        with open(template_file, "r", encoding="utf-8") as f:
            template = f.read()
            return template.format(**kwargs)
    
    # Alapértelmezett template
    return kwargs.get("body", "")

async def send_verification_email(email: str, username: str, token: str, request: Request = None) -> bool:
    """Email verifikációs email küldése"""
    
    # Ha van request, mindig használjuk azt (ez a legmegbízhatóbb)
    if request:
        base_url = f"{request.url.scheme}://{request.url.hostname}"
        if request.url.port and request.url.port not in [80, 443]:
            base_url += f":{request.url.port}"
    else:
        # Ha nincs request, próbáljuk meg a settings.base_url-t használni
        base_url = settings.base_url
        # Ha a base_url üres, rossz formátumú, vagy localhost, akkor hiba
        if not base_url or base_url.startswith("http:///") or base_url.startswith("https:///") or base_url.startswith("http://localhost") or base_url.startswith("https://localhost"):
            logger.error(f"RCON email: base_url nem érvényes: '{base_url}'. Request szükséges az email link generálásához.")
            return False
    
    verification_link = f"{base_url}/verify-email?token={token}"
    logger.info(f"Email verifikációs link generálva: {verification_link}")
    
    # Gamer design template
    body = f"""
    <!DOCTYPE html>
    <html lang="hu">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background: #1a1a2e; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); padding: 30px; text-align: center; border-bottom: 3px solid #667eea;">
                                <h1 style="margin: 0; color: #fff; font-size: 28px; text-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);">
                                    🎮 <span style="color: #667eea;">Zedin</span><span style="color: #764ba2;">Ark</span>Manager
                                </h1>
                                <p style="margin: 10px 0 0 0; color: #a0a0a0; font-size: 14px;">Game Server Management System</p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px; background: #1a1a2e;">
                                <div style="color: #e0e0e0;">
                                    <div style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%); border-left: 4px solid #667eea; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                                        <h2 style="margin: 0 0 15px 0; color: #fff; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                                            <span style="font-size: 32px;">✨</span>
                                            <span>Üdvözöljük a Közösségben!</span>
                                        </h2>
                                        <p style="margin: 0; color: #b0b0b0; font-size: 16px; line-height: 1.6;">
                                            Kedves <strong style="color: #667eea;">{username}</strong>!
                                        </p>
                                    </div>
                                    
                                    <div style="background: #252540; border-radius: 10px; padding: 25px; margin-bottom: 25px; border: 1px solid #3a3a5a;">
                                        <p style="margin: 0 0 20px 0; color: #d0d0d0; font-size: 15px; line-height: 1.7;">
                                            Köszönjük, hogy csatlakoztál hozzánk! Kérjük, erősítsd meg az email címedet a regisztráció befejezéséhez.
                                        </p>
                                        
                                        <div style="text-align: center; margin-top: 30px;">
                                            <a href="{verification_link}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; text-decoration: none; padding: 15px 40px; border-radius: 8px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);">
                                                ✅ Email Megerősítése
                                            </a>
                                        </div>
                                        
                                        <p style="margin: 25px 0 0 0; color: #888; font-size: 13px; text-align: center;">
                                            Vagy másold be ezt a linket: <br>
                                            <a href="{verification_link}" style="color: #667eea; word-break: break-all;">{verification_link}</a>
                                        </p>
                                    </div>
                                    
                                    <div style="background: rgba(102, 126, 234, 0.1); border-left: 4px solid #667eea; padding: 15px; border-radius: 6px; margin-top: 20px;">
                                        <p style="margin: 0; color: #b0b0b0; font-size: 13px; line-height: 1.6;">
                                            <strong style="color: #667eea;">⚠️ Fontos:</strong> A link 24 órán belül lejár. Ha nem kérted ezt az emailt, kérjük hagyd figyelmen kívül.
                                        </p>
                                    </div>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background: #0f0f1e; padding: 25px 30px; text-align: center; border-top: 2px solid #2a2a3e;">
                                <p style="margin: 0; color: #888; font-size: 12px;">
                                    © 2024 ZedinArkManager | Game Server Management
                                </p>
                                <p style="margin: 10px 0 0 0; color: #666; font-size: 11px;">
                                    Ez egy automatikus üzenet, kérjük ne válaszolj rá.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return await send_email(email, "✨ Email Megerősítés - ZedinArkManager", body)

async def send_token_notification(email: str, username: str, token: str, token_type: str, expires_at: str) -> bool:
    """Token értesítő email"""
    activation_link = f"{settings.base_url}/tokens/activate?token={token}"
    type_text = "Szerver Admin" if token_type == "server_admin" else "Felhasználó"
    
    # Gamer design template
    body = f"""
    <!DOCTYPE html>
    <html lang="hu">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background: #1a1a2e; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); padding: 30px; text-align: center; border-bottom: 3px solid #667eea;">
                                <h1 style="margin: 0; color: #fff; font-size: 28px; text-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);">
                                    🎮 <span style="color: #667eea;">Zedin</span><span style="color: #764ba2;">Ark</span>Manager
                                </h1>
                                <p style="margin: 10px 0 0 0; color: #a0a0a0; font-size: 14px;">Game Server Management System</p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px; background: #1a1a2e;">
                                <div style="color: #e0e0e0;">
                                    <div style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%); border-left: 4px solid #667eea; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                                        <h2 style="margin: 0 0 15px 0; color: #fff; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                                            <span style="font-size: 32px;">🔑</span>
                                            <span>Új Token Generálva!</span>
                                        </h2>
                                        <p style="margin: 0; color: #b0b0b0; font-size: 16px; line-height: 1.6;">
                                            Kedves <strong style="color: #667eea;">{username}</strong>!
                                        </p>
                                    </div>
                                    
                                    <div style="background: #252540; border-radius: 10px; padding: 25px; margin-bottom: 25px; border: 1px solid #3a3a5a;">
                                        <p style="margin: 0 0 20px 0; color: #d0d0d0; font-size: 15px; line-height: 1.7;">
                                            Ön számára egy új <strong style="color: #764ba2;">{type_text}</strong> token lett generálva.
                                        </p>
                                        
                                        <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #3a3a5a;">
                                            <div style="margin-bottom: 15px;">
                                                <span style="color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Token</span>
                                                <div style="background: #0f0f1e; padding: 15px; border-radius: 6px; margin-top: 8px; border: 1px solid #2a2a3e;">
                                                    <code style="color: #667eea; font-size: 16px; font-weight: bold; letter-spacing: 1px; word-break: break-all;">{token}</code>
                                                </div>
                                            </div>
                                            
                                            <div style="margin-bottom: 15px;">
                                                <span style="color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Lejárat</span>
                                                <div style="color: #d0d0d0; font-size: 14px; margin-top: 8px;">
                                                    <span style="color: #764ba2;">⏰</span> {expires_at}
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <div style="text-align: center; margin-top: 30px;">
                                            <button onclick="navigator.clipboard.writeText('{token}'); alert('Token másolva a vágólapra!');" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; border: none; padding: 15px 40px; border-radius: 8px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); cursor: pointer;">
                                                📋 Token Másolása Vágólapra
                                            </button>
                                        </div>
                                    </div>
                                    
                                    <div style="background: rgba(102, 126, 234, 0.1); border-left: 4px solid #667eea; padding: 15px; border-radius: 6px; margin-top: 20px;">
                                        <p style="margin: 0; color: #b0b0b0; font-size: 13px; line-height: 1.6;">
                                            <strong style="color: #667eea;">💡 Tipp:</strong> Másold ki a tokent és használd a weboldalon a token aktiválásához!
                                        </p>
                                    </div>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background: #0f0f1e; padding: 25px 30px; text-align: center; border-top: 2px solid #2a2a3e;">
                                <p style="margin: 0; color: #888; font-size: 12px;">
                                    © 2024 ZedinArkManager | Game Server Management
                                </p>
                                <p style="margin: 10px 0 0 0; color: #666; font-size: 11px;">
                                    Ez egy automatikus üzenet, kérjük ne válaszolj rá.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return await send_email(email, "🔑 Új Token Generálva - ZedinArkManager", body)

async def send_token_expiry_warning(email: str, username: str, token: str, days_left: int) -> bool:
    """Token lejárat figyelmeztetés"""
    body = f"""
    <!DOCTYPE html>
    <html lang="hu">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background: #1a1a2e; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); padding: 30px; text-align: center; border-bottom: 3px solid #f59e0b;">
                                <h1 style="margin: 0; color: #fff; font-size: 28px; text-shadow: 0 2px 10px rgba(245, 158, 11, 0.5);">
                                    🎮 <span style="color: #667eea;">Zedin</span><span style="color: #764ba2;">Ark</span>Manager
                                </h1>
                                <p style="margin: 10px 0 0 0; color: #a0a0a0; font-size: 14px;">Game Server Management System</p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px; background: #1a1a2e;">
                                <div style="color: #e0e0e0;">
                                    <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(239, 68, 68, 0.1) 100%); border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                                        <h2 style="margin: 0 0 15px 0; color: #fff; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                                            <span style="font-size: 32px;">⏰</span>
                                            <span>Token Lejárat Figyelmeztetés</span>
                                        </h2>
                                        <p style="margin: 0; color: #b0b0b0; font-size: 16px; line-height: 1.6;">
                                            Kedves <strong style="color: #f59e0b;">{username}</strong>!
                                        </p>
                                    </div>
                                    
                                    <div style="background: #252540; border-radius: 10px; padding: 25px; margin-bottom: 25px; border: 1px solid #3a3a5a;">
                                        <div style="background: rgba(245, 158, 11, 0.2); border: 2px solid #f59e0b; border-radius: 8px; padding: 20px; margin-bottom: 20px; text-align: center;">
                                            <p style="margin: 0; color: #fff; font-size: 18px; font-weight: bold;">
                                                <span style="font-size: 24px;">⚠️</span> Fontos!
                                            </p>
                                            <p style="margin: 10px 0 0 0; color: #f59e0b; font-size: 28px; font-weight: bold;">
                                                {days_left} nap
                                            </p>
                                            <p style="margin: 5px 0 0 0; color: #d0d0d0; font-size: 14px;">
                                                múlva lejár a tokenje!
                                            </p>
                                        </div>
                                        
                                        <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; margin: 20px 0; border: 1px solid #3a3a5a;">
                                            <span style="color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Token</span>
                                            <div style="background: #0f0f1e; padding: 15px; border-radius: 6px; margin-top: 8px; border: 1px solid #2a2a3e;">
                                                <code style="color: #f59e0b; font-size: 16px; font-weight: bold; letter-spacing: 1px; word-break: break-all;">{token}</code>
                                            </div>
                                        </div>
                                        
                                        <p style="margin: 20px 0 0 0; color: #d0d0d0; font-size: 14px; line-height: 1.7;">
                                            Kérjük, aktiváld a tokent a lejárat előtt, hogy ne veszítsd el a hozzáférésedet!
                                        </p>
                                    </div>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background: #0f0f1e; padding: 25px 30px; text-align: center; border-top: 2px solid #2a2a3e;">
                                <p style="margin: 0; color: #888; font-size: 12px;">
                                    © 2024 ZedinArkManager | Game Server Management
                                </p>
                                <p style="margin: 10px 0 0 0; color: #666; font-size: 11px;">
                                    Ez egy automatikus üzenet, kérjük ne válaszolj rá.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return await send_email(email, "⏰ Token Lejárat Figyelmeztetés - ZedinArkManager", body)

async def send_notification_email(email: str, username: str, title: str, message: str) -> bool:
    """Értesítés email küldése"""
    body = f"""
    <!DOCTYPE html>
    <html lang="hu">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background: #1a1a2e; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); padding: 30px; text-align: center; border-bottom: 3px solid #667eea;">
                                <h1 style="margin: 0; color: #fff; font-size: 28px; text-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);">
                                    🎮 <span style="color: #667eea;">Zedin</span><span style="color: #764ba2;">Ark</span>Manager
                                </h1>
                                <p style="margin: 10px 0 0 0; color: #a0a0a0; font-size: 14px;">Game Server Management System</p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px; background: #1a1a2e;">
                                <div style="color: #e0e0e0;">
                                    <div style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%); border-left: 4px solid #667eea; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                                        <h2 style="margin: 0 0 15px 0; color: #fff; font-size: 24px; display: flex; align-items: center; gap: 10px;">
                                            <span style="font-size: 32px;">📢</span>
                                            <span>{title}</span>
                                        </h2>
                                        <p style="margin: 0; color: #b0b0b0; font-size: 16px; line-height: 1.6;">
                                            Kedves <strong style="color: #667eea;">{username}</strong>!
                                        </p>
                                    </div>
                                    
                                    <div style="background: #252540; border-radius: 10px; padding: 25px; margin-bottom: 25px; border: 1px solid #3a3a5a;">
                                        <div style="background: #1a1a2e; border-radius: 8px; padding: 20px; border: 1px solid #3a3a5a; color: #d0d0d0; font-size: 15px; line-height: 1.8;">
                                            {message.replace(chr(10), '<br>')}
                                        </div>
                                    </div>
                                    
                                    <div style="background: rgba(102, 126, 234, 0.1); border-left: 4px solid #667eea; padding: 15px; border-radius: 6px; margin-top: 20px;">
                                        <p style="margin: 0; color: #b0b0b0; font-size: 13px; line-height: 1.6;">
                                            Üdvözlettel,<br>
                                            <strong style="color: #667eea;">ZedinArkManager</strong> csapat
                                        </p>
                                    </div>
                                </div>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background: #0f0f1e; padding: 25px 30px; text-align: center; border-top: 2px solid #2a2a3e;">
                                <p style="margin: 0; color: #888; font-size: 12px;">
                                    © 2024 ZedinArkManager | Game Server Management
                                </p>
                                <p style="margin: 10px 0 0 0; color: #666; font-size: 11px;">
                                    Ez egy automatikus üzenet, kérjük ne válaszolj rá.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return await send_email(email, f"📢 {title} - ZedinArkManager", body)

