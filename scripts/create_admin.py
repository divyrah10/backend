"""
Script to create an admin user
Run with: python scripts/create_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.core.security import get_password_hash
from app.core.permissions import RoleName


def create_admin():
    db = SessionLocal()

    try:
        # Get super admin role
        admin_role = db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN.value).first()

        if not admin_role:
            print("Error: Super admin role not found. Please run migrations first.")
            return

        # Check if admin already exists
        existing = db.query(User).filter(User.email == "admin@loremipsum.com").first()
        if existing:
            print("Admin user already exists.")
            return

        # Create admin user
        admin_user = User(
            email="admin@loremipsum.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin User",
            is_active=True,
            is_verified=True,
            role_id=admin_role.id,
        )

        db.add(admin_user)
        db.commit()

        print("Admin user created successfully!")
        print("Email: admin@loremipsum.com")
        print("Password: admin123")
        print("\nPlease change the password after first login.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
