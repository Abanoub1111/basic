from email_assistant.basic.bootstrap import build_process_email_service
from email_assistant.basic.interfaces.http.app import create_app


app = create_app(build_process_email_service())
