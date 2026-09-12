import getpass
import sys
from app.database import connect
from app.security import hash_password


def main():
    print("Create MemoryBank administrator")
    username = input("Username: ").strip()
    if not username:
        raise SystemExit("Username is required")
    display_name = input("Display name (optional): ").strip() or None
    password = getpass.getpass("Password (12+ chars recommended): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    if len(password) < 10:
        raise SystemExit("Use at least 10 characters")

    with connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE lower(username)=lower(%s)", (username,)).fetchone()
        if existing:
            raise SystemExit("That username already exists")
        row = conn.execute(
            """
            INSERT INTO users(username, display_name, password_hash, is_admin)
            VALUES (%s,%s,%s,true)
            RETURNING id, username
            """,
            (username, display_name, hash_password(password)),
        ).fetchone()
        conn.commit()
    print(f"Created admin {row['username']} ({row['id']})")


if __name__ == "__main__":
    main()
