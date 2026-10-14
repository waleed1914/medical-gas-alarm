"""Create private local/cloud configuration files for a fresh repository clone."""

import json
import secrets
from getpass import getpass
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parent


def load(name):
    with (ROOT / name).open("r", encoding="utf-8") as file:
        return json.load(file)


def save(name, data):
    with (ROOT / name).open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def main():
    username = input("Dashboard username [admin]: ").strip() or "admin"
    password = getpass("Dashboard password: ")
    confirmation = getpass("Confirm password: ")
    if not password or password != confirmation:
        raise SystemExit("Passwords are empty or do not match; no files were changed.")

    password_hash = generate_password_hash(password)
    ingest_token = secrets.token_urlsafe(32)

    web = load("web_config.example.json")
    cloud = load("cloud_config.example.json")
    web["username"] = username
    web["password_hash"] = password_hash
    web["secret_key"] = secrets.token_hex(32)
    web["cloud"]["token"] = ingest_token
    cloud["username"] = username
    cloud["password_hash"] = password_hash
    cloud["secret_key"] = secrets.token_hex(32)
    cloud["ingest_token"] = ingest_token

    save("web_config.json", web)
    save("cloud_config.json", cloud)
    print("Created web_config.json and cloud_config.json with matching private credentials.")


if __name__ == "__main__":
    main()
