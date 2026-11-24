from djnext import desktop


def test_data_folder_is_prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "support"
    desktop.prepare_data_dir(home)
    assert (home / "data").is_dir() and (home / "config.yaml").exists()
