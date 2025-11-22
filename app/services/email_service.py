"""
Email szolgáltatás
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
        
        # SMTP beállítások lekérése (Exim konfigurációból vagy settings-ből)
        smtp_config = get_smtp_settings(domain)
        
        # Ha van Exim konfiguráció, azt használjuk, különben a settings-ből
        smtp_host = smtp_config.get('host') or settings.smtp_host
        smtp_port = smtp_config.get('port') or settings.smtp_port
        smtp_user = smtp_config.get('user') or settings.smtp_user
        smtp_pass = smtp_config.get('pass') or settings.smtp_pass
        use_tls = smtp_config.get('use_tls', False)
        
        # TLS beállítások
        # Port 465 = SSL/TLS (use_tls=True)
        # Port 587 = STARTTLS (start_tls=True)
        # Port 25 = általában nincs TLS
        use_tls_param = (smtp_port == 465)
        start_tls_param = (smtp_port == 587)
        
        await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user if smtp_user else None,
            password=smtp_pass if smtp_pass else None,
            use_tls=use_tls_param,
            start_tls=start_tls_param
        )
        
        return True
    except Exception as e:
        print(f"Email sending error: {e}")
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

async def send_verification_email(email: str, username: str, token: str) -> bool:
    """Email verifikációs email küldése"""
    verification_link = f"{settings.base_url}/verify-email?token={token}"
    
    body = get_email_template(
        "verification",
        username=username,
        verification_link=verification_link,
        base_url=settings.base_url
    )
    
    if not body:
        body = f"""
        <html>
        <body>
            <h2>Üdvözöljük, {username}!</h2>
            <p>Kérjük, erősítse meg az email címét a regisztráció befejezéséhez.</p>
            <a href="{verification_link}">Email megerősítése</a>
            <p>Vagy másolja be ezt a linket: {verification_link}</p>
        </body>
        </html>
        """
    
    return await send_email(email, "Email megerősítés - ZedinArkManager", body)

async def send_token_notification(email: str, username: str, token: str, token_type: str, expires_at: str) -> bool:
    """Token értesítő email"""
    activation_link = f"{settings.base_url}/tokens/activate?token={token}"
    type_text = "Szerver Admin" if token_type == "server_admin" else "Felhasználó"
    
    body = f"""
    <html>
    <body>
        <h2>Új token generálva</h2>
        <p>Kedves {username}!</p>
        <p>Ön számára egy új <strong>{type_text}</strong> token lett generálva.</p>
        <p>Token: <strong>{token}</strong></p>
        <p>Lejárat: {expires_at}</p>
        <a href="{activation_link}">Token aktiválása</a>
    </body>
    </html>
    """
    
    return await send_email(email, "Új token - ZedinArkManager", body)

async def send_token_expiry_warning(email: str, username: str, token: str, days_left: int) -> bool:
    """Token lejárat figyelmeztetés"""
    body = f"""
    <html>
    <body>
        <h2>Token lejárat figyelmeztetés</h2>
        <p>Kedves {username}!</p>
        <p><strong>Fontos:</strong> Tokenje <strong>{days_left} nap</strong> múlva lejár!</p>
        <p>Token: <strong>{token}</strong></p>
    </body>
    </html>
    """
    
    return await send_email(email, "Token lejárat figyelmeztetés - ZedinArkManager", body)

async def send_notification_email(email: str, username: str, title: str, message: str) -> bool:
    """Értesítés email küldése"""
    body = f"""
    <html>
    <body>
        <h2>{title}</h2>
        <p>Kedves {username}!</p>
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
            {message.replace(chr(10), '<br>')}
        </div>
        <p>Üdvözlettel,<br>ZedinArkManager csapat</p>
    </body>
    </html>
    """
    
    return await send_email(email, f"{title} - ZedinArkManager", body)

