from __future__ import annotations

import getpass
from pathlib import Path

from app.core.security import AuthManager


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    auth_manager = AuthManager(base_dir)
    default_username = "admin"
    username = input(f"Usuario [{default_username}]: ").strip() or default_username
    role = input("Rol [admin/operator] (admin): ").strip() or "admin"
    if role not in {"admin", "operator"}:
        raise SystemExit("El rol debe ser admin u operator")
    password = getpass.getpass("Nueva contraseña: ")
    confirm = getpass.getpass("Confirmar contraseña: ")

    if password != confirm:
        raise SystemExit("Las contraseñas no coinciden")
    if len(password) < 12:
        raise SystemExit("La contraseña debe tener al menos 12 caracteres")

    auth_manager.upsert_user(username, password_hash=auth_manager.hash_password(password), role=role, is_active=True)
    print(f"Credenciales actualizadas en PostgreSQL para el usuario {username} con rol {role}")


if __name__ == "__main__":
    main()
