import os
import re
import pathlib
import smtplib
from email.mime.text import MIMEText
from typing import Optional
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

APARTMENT_URL = os.getenv("APARTMENT_URL")
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "999999"))

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME") or EMAIL_FROM
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Separate state file so it does not collide with the SMS-based script
LAST_PRICE_FILE = pathlib.Path("last_notified_price_email.txt")


def get_current_price() -> float:
    """
    Fetch price from:
    <span data-jd-fp-adp="display" class="jd-fp-strong-text">Base Rent $2,671</span>
    """
    if not APARTMENT_URL:
        raise RuntimeError("APARTMENT_URL is not set. Check your .env file.")

    resp = requests.get(APARTMENT_URL, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    span = soup.select_one('span[data-jd-fp-adp="display"].jd-fp-strong-text')
    if not span or not span.get_text(strip=True):
        raise ValueError(
            'Price element not found with selector '
            'span[data-jd-fp-adp="display"].jd-fp-strong-text'
        )

    text = span.get_text(strip=True)  # e.g. "Base Rent $2,671"

    match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*)", text)
    if not match:
        raise ValueError(f"Could not parse price from: {text!r}")

    price_str = match.group(1).replace(",", "")
    return float(price_str)


def send_email(subject: str, body: str) -> None:
    """
    Send an email using the configured SMTP server.
    """
    if not all([SMTP_SERVER, SMTP_PORT, EMAIL_FROM, EMAIL_TO, EMAIL_USERNAME, EMAIL_PASSWORD]):
        raise RuntimeError("Email settings are incomplete. Check your .env file.")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)


def get_last_notified_price() -> Optional[float]:
    if not LAST_PRICE_FILE.exists():
        return None
    try:
        content = LAST_PRICE_FILE.read_text().strip()
        return float(content)
    except Exception:
        return None


def set_last_notified_price(price: float) -> None:
    LAST_PRICE_FILE.write_text(str(price))


def main():
    try:
        current_price = get_current_price()
    except Exception as e:
        print(f"Error fetching/parsing price: {e}")
        return

    print(f"Current price: {current_price}")

    if current_price > PRICE_THRESHOLD:
        print(f"Price is above threshold ({PRICE_THRESHOLD}). No email sent.")
        return

    last_price = get_last_notified_price()

    # Only notify if:
    #  - we never notified before, or
    #  - the current price is different (usually lower) than last notified
    if last_price is not None and current_price >= last_price:
        print(
            f"Price {current_price} is not lower than last notified price {last_price}. "
            f"No email sent."
        )
        return

    subject = "Apartment price alert"
    body = (
        f"Apartment price alert!\n\n"
        f"Current quote: ${current_price:,.0f}\n"
        f"Threshold: ${PRICE_THRESHOLD:,.0f}\n"
        f"URL: {APARTMENT_URL}\n"
    )

    print("Sending email...")
    try:
        send_email(subject, body)
        set_last_notified_price(current_price)
        print("Email sent.")
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    main()
