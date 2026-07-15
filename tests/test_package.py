def test_smoke() -> None:
    assert True


def test_cli_main_returns_success() -> None:
    from lza_workbench.cli import main

    assert main([]) == 0


def test_cli_version_option(capsys) -> None:
    from lza_workbench import __version__
    from lza_workbench.cli import main

    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
