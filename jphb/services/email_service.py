import os
import dotenv

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

dotenv.load_dotenv()


class EmailService:

    def __init__(self, email: str = os.getenv('SMTP_EMAIL', 'INVALID_EMAIL'),
                 password: str = os.getenv('SMTP_PASSWORD', 'INVALID_PASSWORD')):
        self.email = email
        self.password = password

    def send_email(self, to_email: str, subject: str, message: str) -> bool:
        msg = MIMEMultipart()
        msg['From'] = self.email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))

        try:
            server = smtplib.SMTP(os.getenv('SMTP_SERVER', 'INVALID_SMTP_SERVER'), int(os.getenv('SMTP_PORT', '587')))
            server.starttls()
            server.login(self.email, self.password)
            server.sendmail(self.email, to_email, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            return False
