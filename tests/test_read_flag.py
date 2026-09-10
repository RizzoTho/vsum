"""--read flag semantics and old-flag migration, using build_parser/main only (no network)."""

from __future__ import annotations

import pytest

from conftest import load_vsum


def test_read_absent(vsum):
    args = vsum.build_parser().parse_args(["run", "https://example.com/v"])
    assert args.read is None


def test_read_bare_flag_uses_default(vsum):
    args = vsum.build_parser().parse_args(["run", "https://example.com/v", "--read"])
    assert args.read == vsum.DEFAULT_READ_INTENT


def test_read_with_value_is_verbatim(vsum):
    args = vsum.build_parser().parse_args(["run", "https://example.com/v", "--read", "重点讲演示流程"])
    assert args.read == "重点讲演示流程"


def test_url_before_read(vsum):
    args = vsum.build_parser().parse_args(["run", "https://example.com/v", "--read", "目的"])
    assert args.url == "https://example.com/v"


def test_removed_intent_flag_gives_migration_hint(vsum, capsys):
    code = vsum.main(["run", "https://example.com/v", "--intent", "x"])
    assert code == 1
    err = capsys.readouterr().err
    assert "--intent" in err and "--read" in err


def test_removed_readable_flag_gives_migration_hint(vsum, capsys):
    code = vsum.main(["run", "https://example.com/v", "--readable", "openai"])
    assert code == 1
    err = capsys.readouterr().err
    assert "--readable" in err and "READABLE.md" in err


def test_removed_readable_model_flag(vsum, capsys):
    assert vsum.main(["run", "u", "--readable-model", "gpt"]) == 1


def test_download_flag_is_noop_warning(vsum, monkeypatch, capsys):
    recorded = {}

    def fake_run_brief(args):
        recorded["download"] = getattr(args, "download", None)
        return 0

    monkeypatch.setattr(vsum, "run_brief", fake_run_brief)
    code = vsum.main(["run", "https://example.com/v", "--download"])
    assert code == 0
    err = capsys.readouterr().err
    assert "no-op" in err
    # download never becomes an argparse flag at all
    args = vsum.build_parser().parse_args(["run", "u"])
    assert not hasattr(args, "download")


def test_blank_read_purpose_errors_before_network(vsum, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("network must not be touched for a blank purpose")

    monkeypatch.setattr(vsum, "dump_metadata", boom)
    code = vsum.main(["run", "https://example.com/v", "--read", "   "])
    assert code == 1
    assert "blank" in capsys.readouterr().err
