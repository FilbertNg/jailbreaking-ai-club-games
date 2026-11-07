import pytest

from jailbreak.config import ROOT, ConfigError, load_config, load_settings, parse_config


def test_parse_valid_config(cfg):
    assert cfg.models == ("m1", "m2", "m3")
    assert len(cfg.rounds) == 3
    assert cfg.rounds[2].censor == "strict"
    assert cfg.tiebreaker.difficulty == "Tiebreaker"
    assert cfg.team_names == {"a": "Team A", "b": "Team B"}
    assert cfg.rounds[2].easier_option == 2
    assert cfg.rounds[0].easier_option is None
    assert cfg.rounds[0].minutes == 3


def test_real_config_json_is_valid():
    cfg = load_config(ROOT / "config.json")
    assert cfg.models[0] == "gemini-3.5-flash-lite"


def test_prompt_without_code_placeholder_is_rejected(test_config_dict):
    test_config_dict["rounds"][0]["prompt"] = "no placeholder"
    with pytest.raises(ConfigError, match="rounds\\[0\\]"):
        parse_config(test_config_dict)


def test_unknown_censor_is_rejected(test_config_dict):
    test_config_dict["tiebreaker"]["censor"] = "loud"
    with pytest.raises(ConfigError, match="censor"):
        parse_config(test_config_dict)


def test_missing_key_is_named(test_config_dict):
    del test_config_dict["tie_window_s"]
    with pytest.raises(ConfigError, match="tie_window_s"):
        parse_config(test_config_dict)


def test_missing_round_minutes_is_named(test_config_dict):
    del test_config_dict["rounds"][1]["minutes"]
    with pytest.raises(ConfigError, match="rounds\\[1\\].*minutes"):
        parse_config(test_config_dict)


def test_easier_option_must_point_back(test_config_dict):
    test_config_dict["rounds"][2]["easier_option"] = 3
    with pytest.raises(ConfigError, match="easier_option"):
        parse_config(test_config_dict)


def test_missing_api_key_stops_startup(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("HOST_PIN=1234\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        load_settings(env)


def test_settings_read_pin(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("HOST_PIN", raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=abc\nHOST_PIN=4321\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.host_pin == "4321"


def test_blank_pin_means_no_host_controls(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("HOST_PIN", raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=abc\n", encoding="utf-8")
    assert load_settings(env).host_pin is None
