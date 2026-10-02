"""IMAP-Abruf: nur lesend, nur relevante/neue Mails, Fehlerfälle, Engine-Integration."""
import imaplib
import json
import logging
import socket

import pytest

from pakettracker import config, engine
from pakettracker.sources.imap import ImapSource, ImapSourceError, encode_folder

from conftest import FIXTURES

log = logging.getLogger("test")
PASSWORD = "imap-pass-NICHT-ECHT"


class FakeImap:
    """Minimaler IMAP-Server im Speicher; protokolliert alle Zugriffe."""

    def __init__(self, folders, login_ok=True):
        self.folders = folders  # {name: {"uidvalidity": "1", "messages": {uid: bytes}}}
        self.login_ok = login_ok
        self.calls = []
        self.current = None

    def __call__(self, host, port, security, context, timeout):
        self.calls.append(("connect", host, port, security))
        return self

    def login(self, user, password):
        self.calls.append(("login", user))
        if not self.login_ok:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials")

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        name = mailbox.strip('"')
        self.current = self.folders.get(name)
        return ("OK", [b"1"]) if self.current is not None else ("NO", [b"no such folder"])

    def response(self, code):
        return code, [self.current["uidvalidity"].encode()]

    def uid(self, command, *args):
        self.calls.append(("uid", command) + args)
        messages = self.current["messages"]
        if command == "SEARCH":
            return "OK", [" ".join(str(u) for u in sorted(messages)).encode()]
        if command == "FETCH":
            uids, spec = [int(u) for u in args[0].split(",")], args[1]
            data = []
            for uid in uids:
                raw = messages[uid]
                if "HEADER.FIELDS" in spec:
                    header = raw.split(b"\n\n", 1)[0] + b"\n\n"
                    data += [(f"1 (UID {uid} RFC822.SIZE {len(raw)} BODY[HEADER.FIELDS (FROM)] {{1}}".encode(),
                              header), b")"]
                else:
                    assert "BODY.PEEK[]" in spec  # nie \\Seen setzen
                    data += [(f"1 (UID {uid} BODY[] {{1}}".encode(), raw), b")"]
            return "OK", data
        if command == "STORE":
            return "OK", [b""]
        raise AssertionError(command)

    def logout(self):
        self.calls.append(("logout",))

    def commands(self, name):
        return [c for c in self.calls if c[0] == "uid" and c[1] == name]


def fixture(name):
    return (FIXTURES / name).read_bytes()


def mailbox(**messages):
    return {"INBOX": {"uidvalidity": "1", "messages": dict(messages)}}


SETTINGS = {"host": "imap.example.invalid", "port": 993, "security": "ssl", "user": "max", "password": PASSWORD,
            "folder": "INBOX", "lookback_days": 14, "mark_processed": False}


def source(fake, state=None, **overrides):
    is_carrier = lambda sender: any(d in sender for d in ("dhl.de", "myhermes.de", "amazon.de"))
    return ImapSource({**SETTINGS, **overrides}, log, state if state is not None else {}, is_carrier, fake)


def test_reads_only_relevant_mails_read_only():
    fake = FakeImap({"INBOX": {"uidvalidity": "7", "messages": {
        1: fixture("dhl_announcement.eml"), 2: fixture("other_sender.eml"), 3: fixture("hermes_today.eml")}}})
    mails = source(fake).fetch()
    assert sorted(m.subject for m in mails) == ["Ihr DHL Paket kommt am Montag", "Ihre Hermes Sendung wird heute zugestellt"]
    assert ("select", '"INBOX"', True) in fake.calls           # read-only
    assert len(fake.commands("FETCH")) == 3                     # 1× Header, 2× Inhalt relevanter Mails
    assert fake.commands("STORE") == []                         # nichts markiert, nichts gelöscht
    assert fake.calls[-1] == ("logout",)


def test_only_new_mails_on_next_run():
    state = {}
    fake = FakeImap(mailbox(**{"5": fixture("dhl_announcement.eml")}))
    fake.folders["INBOX"]["messages"] = {5: fixture("dhl_announcement.eml")}
    assert len(source(fake, state).fetch()) == 1
    assert state["folders"]["INBOX"] == {"uidvalidity": "1", "last_uid": 5}
    assert source(fake, state).fetch() == []                    # nichts Neues

    fake.folders["INBOX"]["messages"][6] = fixture("hermes_today.eml")
    [mail] = source(fake, state).fetch()
    assert mail.subject.startswith("Ihre Hermes")


def test_uidvalidity_change_rescans():
    state = {"folders": {"INBOX": {"uidvalidity": "1", "last_uid": 99}}}
    fake = FakeImap({"INBOX": {"uidvalidity": "2", "messages": {3: fixture("dhl_announcement.eml")}}})
    assert len(source(fake, state).fetch()) == 1


def test_mark_processed_sets_own_keyword_only():
    fake = FakeImap({"INBOX": {"uidvalidity": "1", "messages": {4: fixture("dhl_announcement.eml")}}})
    source(fake, mark_processed=True).fetch()
    assert ("select", '"INBOX"', False) in fake.calls
    [store] = fake.commands("STORE")
    assert store[2:] == ("4", "+FLAGS.SILENT", "($Pakettracker)")


def test_login_failure_without_password_in_message():
    with pytest.raises(ImapSourceError) as info:
        source(FakeImap(mailbox(), login_ok=False)).fetch()
    assert "Anmeldung fehlgeschlagen" in str(info.value) and PASSWORD not in str(info.value)


def test_missing_settings():
    with pytest.raises(ImapSourceError):
        source(FakeImap(mailbox()), password="").fetch()


def test_connection_refused():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    imap = ImapSource({**SETTINGS, "host": "127.0.0.1", "port": port, "security": "none"}, log, {})
    imap._factory = None
    with pytest.raises(ImapSourceError) as info:
        imap.fetch()
    assert "nicht erreichbar" in str(info.value)


def test_multiple_folders_one_missing():
    fake = FakeImap({"INBOX": {"uidvalidity": "1", "messages": {1: fixture("dhl_announcement.eml")}},
                     "Pakete": {"uidvalidity": "1", "messages": {1: fixture("hermes_today.eml")}}})
    mails = source(fake, folder="INBOX, Gibtsnicht, Pakete").fetch()
    assert len(mails) == 2
    with pytest.raises(ImapSourceError):
        source(fake, folder="Gibtsnicht").fetch()


def test_folder_encoding():
    assert encode_folder("INBOX") == '"INBOX"'
    assert encode_folder("Bestätigt") == '"Best&AOQ-tigt"'
    assert encode_folder('A&B "x"') == '"A&-B \\"x\\""'


def test_connection_test_counts_without_changing_state():
    fake = FakeImap({"INBOX": {"uidvalidity": "1", "messages": {1: fixture("dhl_announcement.eml"),
                                                                2: fixture("other_sender.eml")}}})
    state = {}
    message = source(fake, state).test()
    assert "2 Mails im Zeitraum, 1 von Paketdiensten" in message
    assert state == {} and not [c for c in fake.commands("FETCH") if "BODY.PEEK[]" in c[-1]]


# --- Engine ------------------------------------------------------------------

def _engine_cfg(paths, **email):
    settings = config.defaults()
    settings["general"].update({"mock_mode": False, "max_age_days": 365})
    settings["mqtt"]["enabled"] = False
    settings["email"].update({"enabled": True, "source": "imap", "host": "imap.example.invalid", "user": "max",
                              **email})
    paths.settings_file.write_text(json.dumps(settings))
    creds = json.loads(paths.credentials_file.read_text())
    creds["email"] = {"password": PASSWORD}
    paths.credentials_file.write_text(json.dumps(creds))
    return config.load(paths)


def _with_factory(fake, fn):
    ImapSource.FACTORY = fake
    try:
        return fn()
    finally:
        ImapSource.FACTORY = None


def test_engine_imap_duplicates_across_folders(plugin_root):
    raw = fixture("hermes_today.eml")
    fake = FakeImap({"INBOX": {"uidvalidity": "1", "messages": {1: raw}},
                     "Pakete": {"uidvalidity": "1", "messages": {9: raw}}})
    cfg = _engine_cfg(plugin_root, folder="INBOX, Pakete")
    _with_factory(fake, lambda: engine.run(plugin_root, cfg, force=True))
    state = json.loads(plugin_root.state_file.read_text())
    assert [s["tracking_number"] for s in state["shipments"]] == ["H1000000000000000001"]
    assert state["providers"]["hermes"]["health"] == "ok" and state["email"]["error"] == ""


def test_engine_survives_imap_failure_and_keeps_data(plugin_root):
    cfg = _engine_cfg(plugin_root)
    fake = FakeImap({"INBOX": {"uidvalidity": "1", "messages": {1: fixture("hermes_today.eml")}}})
    _with_factory(fake, lambda: engine.run(plugin_root, cfg, force=True))

    broken = FakeImap(mailbox(), login_ok=False)
    assert _with_factory(broken, lambda: engine.run(plugin_root, cfg, force=True)) == 0
    state = json.loads(plugin_root.state_file.read_text())
    assert [s["tracking_number"] for s in state["shipments"]] == ["H1000000000000000001"]
    assert "Anmeldung fehlgeschlagen" in state["email"]["error"]
    assert state["providers"]["hermes"]["health"] == "error"
    assert state["errors"] == 1 and state["last_full_success"]  # vom ersten, fehlerfreien Lauf
    assert PASSWORD not in plugin_root.state_file.read_text()
    assert PASSWORD not in plugin_root.log_file.read_text() if plugin_root.log_file.exists() else True
