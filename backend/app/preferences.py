"""Instance model selection shared by API and workers."""
from app.config import settings
from app.database import connect


def chat_model():
    with connect() as conn:
        row=conn.execute('SELECT chat_model FROM instance_setup WHERE singleton').fetchone()
    return row['chat_model'] or settings().chat_model
