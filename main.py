import os
import re
import pathlib
import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from dotenv import load_dotenv

# Load .env config
load_dotenv()

APARTMENT_URL = os.getenv("APARTMENT_URL")
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "999999"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")

LAST_PRICE_FILE = pathlib.Path("last_notified_price.txt")


def get_current_price() -> float:
    """
    Fetch price from:
    <span data-jd-fp-adp="display" class="jd-fp-strong-text">Base Rent $2,671</span>
    """
    resp = requests.get(APARTMENT_URL, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    span = soup.select_one('span[data-jd-fp-adp="display"].jd-fp-strong-text')
    if not span or not span.get_text(strip=True):
        raise ValueError(
            "Price element not found: span[data-jd-fp-adp=\"display\"].jd-fp-strong-text"
        )

    text = span.get_text(strip=True)  # e.g. "Base Rent $2,671"

    match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*)", text)
    if not match:
        raise ValueError(f"Could not parse price from: {text!r}")

    price_str = match.group(1).replace(",", "")
    return float(price_str)


def send_sms(message: str) -> None:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=message,
        from_=TWILIO_FROM_NUMBER,
        to=TWILIO_TO_NUMBER,
    )


def get_last_notified_price() -> float:
    if not LAST_PRICE_FILE.exists():
        return 0
    try:
        content = LAST_PRICE_FILE.read_text().strip()
        return float(content)
    except Exception:
        return 0


def set_last_notified_price(price: float) -> None:
    LAST_PRICE_FILE.write_text(str(price))


def main():
    if not APARTMENT_URL:
        raise SystemExit("APARTMENT_URL is not set. Check your .env file.")
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and TWILIO_TO_NUMBER):
        raise SystemExit("Twilio settings are missing. Check your .env file.")

    try:
        current_price = get_current_price()
    except Exception as e:
        # If the site breaks or parsing fails, just print error and exit quietly.
        print(f"Error fetching/parsing price: {e}")
        return

    print(f"Current price: {current_price}")

    if current_price > PRICE_THRESHOLD:
        print(f"Price is above threshold ({PRICE_THRESHOLD}). No SMS sent.")
        return

    last_price = get_last_notified_price()

    # Only notify if:
    #  - we never notified before, or
    #  - the current price is different (usually lower) than last notified
    if last_price != 0 and current_price >= last_price:
        print(f"Price {current_price} is not lower than last notified price {last_price}. No SMS sent.")
        return

    msg = (
        f"Apartment price alert!\n"
        f"Current quote: ${current_price:,.0f}\n"
        f"Threshold: ${PRICE_THRESHOLD:,.0f}\n"
        f"URL: {APARTMENT_URL}"
    )
    print("Sending SMS:", msg)
    send_sms(msg)
    set_last_notified_price(current_price)


if __name__ == "__main__":
    main()
