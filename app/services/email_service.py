"""
Email szolgáltatás
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
from pathlib import Path

async def send_email(to: str, subject: str, body: str, is_html: bool = True) -> bool:
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
        
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user if settings.smtp_user else None,
            password=settings.smtp_pass if settings.smtp_pass else None,
            use_tls=False
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

