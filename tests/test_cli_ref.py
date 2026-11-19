"""`--ref` on the CLI: where an affiliate partner's code comes from and when it is spent.

Covered: `TREG_REF` wins over the code a previous `treg login --ref` or `install.sh --ref` left; a
malformed `--ref` stops the command instead of being dropped; `treg org create` sends the code and
forgets it once the team exists; a sign-in that lands in an existing team forgets it too.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from treg import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.delenv("TREG_REF", raising=False)
    return tmp_path


def test_env_wins_over_the_saved_code(home, monkeypatch):
    cli._remember_ref("jane-doe")
    assert cli._pending_ref() == "jane-doe"
    monkeypatch.setenv("TREG_REF", "Other-Code")
    assert cli._pending_ref() == "other-code"
    monkeypatch.setenv("TREG_REF", "bad code")
    assert cli._pending_ref() == "jane-doe"


def test_install_sh_leaves_the_code_where_the_cli_reads_it(home):
    (home / "ref").write_text("jane-doe\n", encoding="utf-8")
    assert cli._pending_ref() == "jane-doe"


def test_a_malformed_ref_stops_the_command(home):
    with pytest.raises(SystemExit):
        cli._ref_from_args(SimpleNamespace(ref="x;y"))
    assert cli._ref_from_args(SimpleNamespace(ref="Jane-Doe")) == "jane-doe"
    assert cli._ref_from_args(SimpleNamespace()) == ""


def _fake_client(monkeypatch, sent: list, status: int = 200):
    class Resp:
        status_code = status
        text = ""

        def json(self):
            return {"token": "t", "org": "bob", "org_id": 1, "name": "Bob", "role": "owner"}

    class C:
        def post(self, path, json=None):
            sent.append((path, json))
            return Resp()

    @contextmanager
    def client(cfg):
        yield C()
    monkeypatch.setattr(cli, "_client", client)
    monkeypatch.setattr(cli, "_show", lambda r: None)


def test_org_create_sends_the_saved_code_and_then_forgets_it(home, monkeypatch):
    cli._remember_ref("jane-doe")
    sent: list = []
    _fake_client(monkeypatch, sent)
    cli.cmd_org_create(SimpleNamespace(name="Bob", ref=None), {"base_url": "http://test"})
    assert sent == [("/orgs", {"name": "Bob", "ref": "jane-doe"})]
    assert cli._pending_ref() == ""


def test_org_create_keeps_the_code_when_the_team_was_not_made(home, monkeypatch):
    cli._remember_ref("jane-doe")
    _fake_client(monkeypatch, [], status=403)
    cli.cmd_org_create(SimpleNamespace(name="Bob", ref=None), {"base_url": "http://test"})
    assert cli._pending_ref() == "jane-doe"


def test_org_create_without_a_code_sends_none(home, monkeypatch):
    sent: list = []
    _fake_client(monkeypatch, sent)
    cli.cmd_org_create(SimpleNamespace(name="Bob", ref=None), {"base_url": "http://test"})
    assert sent == [("/orgs", {"name": "Bob"})]


def test_a_sign_in_into_an_existing_team_spends_the_code(home):
    cli._remember_ref("jane-doe")
    cli._settle_ref({"active_org": None})
    assert cli._pending_ref() == "jane-doe"
    cli._settle_ref({"active_org": "acme"})
    assert cli._pending_ref() == ""


def test_login_and_org_create_accept_ref():
    parser = cli.build_parser()
    assert parser.parse_args(["login", "--ref", "jane-doe"]).ref == "jane-doe"
    assert parser.parse_args(["org", "create", "Bob", "--ref", "jane-doe"]).ref == "jane-doe"
