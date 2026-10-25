from __future__ import annotations

from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_list, env_str, load_dotenv, require


def test_env_str_returns_stripped_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESOLVE_TEST_VALUE", "  hello  ")
    assert env_str("RESOLVE_TEST_VALUE") == "hello"


def test_env_str_treats_empty_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESOLVE_TEST_VALUE", "   ")
    assert env_str("RESOLVE_TEST_VALUE", default="fallback") == "fallback"


def test_env_str_required_raises_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESOLVE_TEST_MISSING", raising=False)
    with pytest.raises(ImproperlyConfigured, match="RESOLVE_TEST_MISSING"):
        env_str("RESOLVE_TEST_MISSING", required=True)


def test_require_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESOLVE_TEST_MISSING", raising=False)
    with pytest.raises(ImproperlyConfigured, match="RESOLVE_TEST_MISSING"):
        require("RESOLVE_TEST_MISSING")


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " true "])
def test_env_bool_accepts_true_spellings(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("RESOLVE_TEST_FLAG", raw)
    assert env_bool("RESOLVE_TEST_FLAG") is True


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", "off"])
def test_env_bool_accepts_false_spellings(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("RESOLVE_TEST_FLAG", raw)
    assert env_bool("RESOLVE_TEST_FLAG", default=True) is False


def test_env_bool_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESOLVE_TEST_FLAG", raising=False)
    assert env_bool("RESOLVE_TEST_FLAG", default=True) is True


def test_env_bool_rejects_ambiguous_value_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESOLVE_TEST_FLAG", "sometimes-secret-value")
    with pytest.raises(ImproperlyConfigured) as excinfo:
        env_bool("RESOLVE_TEST_FLAG")

    message = str(excinfo.value)
    assert "RESOLVE_TEST_FLAG" in message
    assert "sometimes-secret-value" not in message


def test_env_int_parses_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESOLVE_TEST_PORT", " 5432 ")
    assert env_int("RESOLVE_TEST_PORT") == 5432

    monkeypatch.delenv("RESOLVE_TEST_PORT")
    assert env_int("RESOLVE_TEST_PORT", default=6379) == 6379


def test_env_int_rejects_non_numeric_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESOLVE_TEST_PORT", "not-a-number-secret")
    with pytest.raises(ImproperlyConfigured) as excinfo:
        env_int("RESOLVE_TEST_PORT")

    assert "RESOLVE_TEST_PORT" in str(excinfo.value)
    assert "not-a-number-secret" not in str(excinfo.value)


def test_env_list_splits_trims_and_drops_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESOLVE_TEST_HOSTS", "localhost, 127.0.0.1 ,,example.com")
    assert env_list("RESOLVE_TEST_HOSTS") == ["localhost", "127.0.0.1", "example.com"]


def test_env_list_returns_default_copy_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESOLVE_TEST_HOSTS", raising=False)
    default: list[str] = []
    result = env_list("RESOLVE_TEST_HOSTS", default=default)
    result.append("mutated")

    assert default == []


def test_load_dotenv_reads_values_and_skips_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RESOLVE_DOTENV_A", raising=False)
    monkeypatch.delenv("RESOLVE_DOTENV_B", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# comment\n\nRESOLVE_DOTENV_A=plain-value\nexport RESOLVE_DOTENV_B = "quoted value"\n'
        "malformed-line-without-equals\n",
        encoding="utf-8",
    )

    load_dotenv(env_file)

    assert env_str("RESOLVE_DOTENV_A") == "plain-value"
    assert env_str("RESOLVE_DOTENV_B") == "quoted value"


def test_load_dotenv_never_overrides_existing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESOLVE_DOTENV_C", "from-process")
    env_file = tmp_path / ".env"
    env_file.write_text("RESOLVE_DOTENV_C=from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert env_str("RESOLVE_DOTENV_C") == "from-process"


def test_load_dotenv_is_a_noop_when_file_is_missing(tmp_path: Path) -> None:
    load_dotenv(tmp_path / "absent.env")
