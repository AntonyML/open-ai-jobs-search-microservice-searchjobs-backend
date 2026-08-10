"""Filtro de spam del canal from_work_home — mensajes basura deben rechazarse.

Comportamiento bajo prueba (público): parse_message para el formato
"from_work_home" devuelve None para spam y mensajes sin señales legítimas,
y parsea los posts legítimos como freetext.
"""

import pytest

from app.parsing import parse_message

pytestmark = pytest.mark.unit

# (descripción, mensaje) — cada uno dispara al menos una señal de spam real.
SPAM_POSTS = [
    ("link de referido de telegram", "Remote Developer Wanted\nApply here: tglink.io/xyz"),
    ("acortador de URLs", "Earn Daily\nMore info: https://tinyurl.com/sk6kzz9"),
    ("descarga de app", "Start Earning\nDownload the app now and join us"),
    ("sin skills / sin inversión", "Make cash online\nNo skills required, no investment needed"),
    ("earn money", "Join our team\nEarn money from your phone, guaranteed"),
    ("make money fast", "Simple trick\nMake money fast from home"),
    ("UPI payment", "Earn rewards\nGet UPI payment cashback daily"),
    ("referral link", "Big opportunity\nUse my referral link to get $10"),
    ("pago por tarea", "Quick tasks\nWe pay per task for easy jobs"),
    ("gift card", "Win prizes\nEnter to win a free gift card"),
    ("crypto airdrop", "Crypto bonus\nTake part in the crypto airdrop today"),
    ("click here to earn", "Great deal\nClick here to earn $5 instantly"),
    ("yapple", "Weird source\nWith yapple you can earn easily"),
    ("earn grams", "Telegram coins\nearn grams by inviting friends"),
    ("withdraw a paytm", "Cash rewards\nYou can withdraw your earnings to Paytm"),
    ("daily earning", "No experience\nStart getting your daily earning"),
    ("data entry desde casa", "Data Entry\nWork from home data entry positions"),
    ("typing part-time", "Typing work\nPart-time typing jobs available"),
]


@pytest.mark.parametrize("label,text", SPAM_POSTS)
def test_spam_posts_are_rejected(label, text):
    assert parse_message(text, "from_work_home", "from_work_home", 1) is None


def test_post_ending_with_image_emoji_is_rejected():
    text = "Amazing passive income offer\nCheck it 🖼"
    assert parse_message(text, "from_work_home", "from_work_home", 1) is None


def test_post_without_legit_signals_is_rejected():
    text = "Promociones y ofertas varias\nDescarga la app hoy mismo"
    assert parse_message(text, "from_work_home", "from_work_home", 1) is None


def test_legit_job_post_is_parsed():
    text = (
        "We are hiring a remote Customer Support Specialist\n"
        "Company: XYZ\n"
        "Salary: $1,500/month\n"
        "Location: Remote\n"
        "Apply via https://jobs.xyz.com/apply"
    )
    result = parse_message(text, "from_work_home", "from_work_home", 1)
    assert result is not None
    assert "Customer Support" in result.title
    assert result.company == "XYZ"