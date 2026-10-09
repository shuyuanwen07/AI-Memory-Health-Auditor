"""Owner-operated password setup; no plaintext password is printed or saved."""
from getpass import getpass
from app.security.access import password_hash


def main():
    password = getpass('New workspace password (12–1024 characters): ')
    if not 12 <= len(password) <= 1024:
        raise SystemExit('Choose a password between 12 and 1024 characters.')
    if password != getpass('Repeat workspace password: '):
        raise SystemExit('The passwords did not match. No configuration was created.')
    # Single quotes protect the dollar-delimited hash from Compose interpolation.
    print("AUDITOR_OPERATOR_PASSWORD_HASH='" + password_hash(password) + "'")


if __name__ == '__main__':
    main()
