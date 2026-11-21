"""Cruscotto su Google Sheet: tre schede che si aggiornano da sole a ogni corsa.

- Stato    : una riga per post (chiave nascosta in colonna A), aggiornata sul posto
             programmato -> pubblicato / FALLITO, con link o motivo.
- Account  : una riga per account Blotato usato dal sistema, con l'ultimo controllo.
- Storico  : tutto quello che succede, una riga per evento (solo aggiunte).
Il cruscotto non deve mai bloccare la pubblicazione: ogni errore qui viene solo scritto nel log.
"""
from __future__ import annotations

STATO_COLS = ["Chiave", "Brand", "Giorno uscita", "Account", "Tipo", "File", "Uscita (ora account)",
              "Uscita (ora Italia)", "Stato", "Aggiornato (ora Italia)", "ID Blotato", "Link / motivo",
              "ID contenuto"]
ACCOUNT_COLS = ["Chiave", "Brand", "Account", "Piattaforma", "ID Blotato", "Stato", "Ultimo controllo (ora Italia)",
                "Note"]
STORICO_COLS = ["Quando (ora Italia)", "Brand", "Giorno uscita", "Account", "Tipo", "File", "Uscita (ora Italia)",
                "Evento", "ID Blotato", "Link / motivo"]
CALENDARIO_COLS = ["Giorno", "Brand", "EN · reel", "EN · carosello", "IT · reel", "IT · carosello"]
NUMERI_COLS = ["Chiave", "Brand", "Giorno uscita", "Account", "Tipo", "ID contenuto", "Views", "Like", "Commenti",
               "Reach", "Condivisioni", "Salvataggi", "Aggiornato (ora Italia)", "Link"]
CHI_COLS = ["Brand", "Chat", "Sta facendo", "Contenuto", "Ultimo segnale (ora Italia)", "Stato"]
TABS = {"Calendario": CALENDARIO_COLS, "Stato": STATO_COLS, "Numeri": NUMERI_COLS, "Chi lavora": CHI_COLS,
        "Account": ACCOUNT_COLS, "Storico": STORICO_COLS}
REPLACE_TABS = ("Calendario", "Chi lavora")  # riscritte da zero a ogni corsa


def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Dashboard:
    def __init__(self, sa_info: dict | None, sheet_id: str | None, log=print):
        self.log = log
        self.svc = None
        self.sheet_id = sheet_id
        self._upserts: dict[str, dict[str, dict]] = {"Stato": {}, "Account": {}, "Numeri": {}}
        self._replace: dict[str, list[list]] = {}
        self._storico: list[list] = []
        if not (sa_info and sheet_id):
            return
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            self.svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
            self._ensure_tabs()
        except Exception as e:
            self.log(f"(cruscotto non disponibile: {str(e)[:200]})")
            self.svc = None

    # ---------- struttura
    def _ensure_tabs(self) -> None:
        ss = self.svc.spreadsheets()
        meta = ss.get(spreadsheetId=self.sheet_id, fields="sheets.properties").execute()
        sheets = {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}
        reqs = []
        if "Storico" not in sheets:  # il primo foglio (nato dal CSV) diventa lo Storico
            first = meta["sheets"][0]["properties"]
            reqs.append({"updateSheetProperties": {"properties": {"sheetId": first["sheetId"], "title": "Storico"},
                                                   "fields": "title"}})
            sheets["Storico"] = first
        for i, t in enumerate(TABS):
            if t not in sheets:
                reqs.append({"addSheet": {"properties": {"title": t, "index": i}}})
        if reqs:
            ss.batchUpdate(spreadsheetId=self.sheet_id, body={"requests": reqs}).execute()
            meta = ss.get(spreadsheetId=self.sheet_id, fields="sheets.properties").execute()
        props = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
        # intestazioni, grassetto, prima riga bloccata, colonna chiave nascosta
        data = [{"range": f"{t}!A1:{_col(len(c))}1", "values": [c]} for t, c in TABS.items()]
        ss.values().batchUpdate(spreadsheetId=self.sheet_id,
                                body={"valueInputOption": "RAW", "data": data}).execute()
        fmt = []
        for t, cols in TABS.items():
            sid = props[t]["sheetId"]
            fmt.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                                       "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                                       "fields": "userEnteredFormat.textFormat.bold"}})
            fmt.append({"updateSheetProperties": {"properties": {"sheetId": sid,
                                                                 "gridProperties": {"frozenRowCount": 1}},
                                                  "fields": "gridProperties.frozenRowCount"}})
            if cols[0] == "Chiave":
                fmt.append({"updateDimensionProperties": {
                    "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                    "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})
        ss.batchUpdate(spreadsheetId=self.sheet_id, body={"requests": fmt}).execute()

    # ---------- API usata dallo script
    def upsert(self, tab: str, key: str, **fields) -> None:
        """Imposta i campi della riga con questa chiave (la crea se non c'è). Si scrive tutto al flush()."""
        self._upserts[tab].setdefault(key, {}).update({k: v for k, v in fields.items() if v is not None})

    def links(self) -> dict[str, str]:
        """URL pubblici già trovati dalle verifiche (scheda Stato): url -> chiave."""
        if not self.svc:
            return {}
        try:
            rows = self.svc.spreadsheets().values().get(spreadsheetId=self.sheet_id,
                                                        range="Stato!A2:M").execute().get("values", [])
            i = STATO_COLS.index("Link / motivo")
            return {r[i].rstrip("/"): r[0] for r in rows if len(r) > i and r[i].startswith("http")}
        except Exception:
            return {}

    def replace(self, tab: str, rows: list[list]) -> None:
        """Riscrive la scheda da zero (sotto l'intestazione) al flush()."""
        self._replace[tab] = rows

    def event(self, row: list) -> None:
        self._storico.append(row)

    def flush(self) -> None:
        if not self.svc:
            return
        try:
            ss = self.svc.spreadsheets().values()
            data = []
            for tab, rows in self._upserts.items():
                if not rows:
                    continue
                cols = TABS[tab]
                existing = ss.get(spreadsheetId=self.sheet_id, range=f"{tab}!A:A").execute().get("values", [])
                index = {r[0]: i + 1 for i, r in enumerate(existing) if r}
                next_row = max(len(existing), 1) + 1  # riga 1 = intestazione
                for key, fields in rows.items():
                    if key in index:
                        for name, val in fields.items():
                            c = cols.index(name) + 1
                            data.append({"range": f"{tab}!{_col(c)}{index[key]}", "values": [[val]]})
                    else:
                        row = [key] + [fields.get(c, "") for c in cols[1:]]
                        data.append({"range": f"{tab}!A{next_row}:{_col(len(cols))}{next_row}", "values": [row]})
                        next_row += 1
            if self._storico:
                n = len(ss.get(spreadsheetId=self.sheet_id, range="Storico!A:A").execute().get("values", []))
                start = max(n, 1) + 1
                end = start + len(self._storico) - 1
                data.append({"range": f"Storico!A{start}:{_col(len(STORICO_COLS))}{end}", "values": self._storico})
            for tab, rows in self._replace.items():
                ss.clear(spreadsheetId=self.sheet_id, range=f"{tab}!A2:Z").execute()
                if rows:
                    data.append({"range": f"{tab}!A2:{_col(len(TABS[tab]))}{len(rows) + 1}", "values": rows})
            if data:
                ss.batchUpdate(spreadsheetId=self.sheet_id,
                               body={"valueInputOption": "USER_ENTERED", "data": data}).execute()
            self.log(f"Cruscotto aggiornato ({sum(len(r) for r in self._upserts.values())} righe di stato, "
                     f"{len(self._storico)} eventi).")
        except Exception as e:
            self.log(f"(cruscotto non aggiornato: {str(e)[:300]})")
