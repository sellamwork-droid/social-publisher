"""Scrive a una chat del portale un messaggio dettato da Power (come se lo scrivesse lui nella chat).

Power, 26/11 19:05: «togli il fatto dei 99 centesimi del dollaro» (finali dei T2 Volwick 02–101): la richiesta va alla chat
che fa quel formato. CHAT = id della chat (es. volwick-t2), TESTO = il messaggio.
"""
from __future__ import annotations

import os

from portale import connect


def main() -> None:
    supa = connect()
    if not supa:
        raise SystemExit("Portale non collegato")
    chat, testo = os.environ["CHAT"].strip(), os.environ["TESTO"].strip()
    if not supa.get("pub_chats", select="id", id=f"eq.{chat}"):
        raise SystemExit(f"chat {chat} non trovata")
    supa.s.post(f"{supa.url}/rest/v1/pub_messages", timeout=60, headers={"Prefer": "return=minimal"},
                json={"chat_id": chat, "autore": "power", "testo": testo, "stato": "nuovo"}).raise_for_status()
    print(f"messaggio scritto a {chat}")


if __name__ == "__main__":
    main()
