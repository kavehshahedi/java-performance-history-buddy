import os
import dotenv
import sys
import traceback

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

dotenv.load_dotenv()


class EmailService:

    def __init__(self, email: str = os.getenv('SMTP_EMAIL', 'INVALID_EMAIL'),
                 password: str = os.getenv('SMTP_PASSWORD', 'INVALID_PASSWORD'),
                 **kwargs):
        self.email = email
        self.password = password

        if kwargs.get('project_name', None):
            self.project_name = kwargs.get('project_name')

        # Send an email if the system crashes during the execution
        sys.excepthook = self.__send_email_on_crash

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
        
    def __send_email_on_crash(self, exc_type, exc_value, exc_traceback):
        self.send_email(os.getenv('SMTP_TO_EMAIL', 'INVALID_TO_EMAIL'),
                        f'System Crash - {self.project_name}',
                        ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
