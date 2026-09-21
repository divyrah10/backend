"""
Script to create an admin user
Run with: python scripts/create_admin.py
"""
import sys
import os
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.core.security import get_password_hash
from app.core.permissions import RoleName


def create_admin():
    email = input("Admin email: ").strip().lower()
    full_name = input("Admin full name: ").strip()
    password = getpass.getpass("Admin password (12+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if not email or "@" not in email or not full_name:
        print("Error: a valid email and full name are required.")
        return
    if len(password) < 12 or password != confirmation:
        print("Error: passwords must match and contain at least 12 characters.")
        return

    db = SessionLocal()

    try:
        # Get super admin role
        admin_role = db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN.value).first()

        if not admin_role:
            print("Error: Super admin role not found. Please run migrations first.")
            return

        # Check if admin already exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print("Admin user already exists.")
            return

        # Create admin user
        admin_user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            is_active=True,
            is_verified=True,
            role_id=admin_role.id,
        )

        db.add(admin_user)
        db.commit()

        print("Admin user created successfully!")
        print(f"Email: {email}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
