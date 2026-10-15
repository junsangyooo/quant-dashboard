"""The deploy files keep their safety properties (audit A2, A4, A8): the unit's environment and
sandbox, nginx's origin gate and headers, the order of deploy.sh's steps, and the crontab block
installer."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from types import ModuleType

import pytest

from autotrade.config import REPO_ROOT

DEPLOY = REPO_ROOT / "deploy"


def directives(text: str) -> list[tuple[str, str]]:
    """(key, value) of a systemd unit, comments and section headers left out."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "[")):
            continue
        key, _, value = line.partition("=")
        out.append((key, value))
    return out


def test_the_unit_reads_no_secrets_and_keeps_live_orders_and_dev_mode_out() -> None:
    unit = directives((DEPLOY / "autotrade.service").read_text())
    keys = [k for k, _ in unit]
    assert "EnvironmentFile" not in keys  # it would win over Environment= (ops notes §9.5)
    unset = " ".join(v for k, v in unit if k == "UnsetEnvironment").split()
    for name in (
        "AUTOTRADE_LIVE_ORDERS",
        "AUTOTRADE_DEV",
        "AUTOTRADE_FAKE_NOW",
        "AUTOTRADE_DB",
        "ANTHROPIC_API_KEY",
        "DART_API_KEY",
        # The web never calls Toss (autotrade/PHASE3.md 2.1): no broker keys in its environment.
        "TOSS_CLIENT_ID",
        "TOSS_CLIENT_SECRET",
        "TOSS_ACCOUNT_NO",
    ):
        assert name in unset, name
    assert not [v for k, v in unit if k == "Environment" and v.startswith("AUTOTRADE_")]


def test_the_unit_is_sandboxed() -> None:
    unit = dict(directives((DEPLOY / "autotrade.service").read_text()))
    expected = {
        "User": "ubuntu",
        "NoNewPrivileges": "yes",
        "CapabilityBoundingSet": "",
        "ProtectSystem": "strict",
        "ProtectHome": "tmpfs",
        "BindReadOnlyPaths": "/home/ubuntu/quant-dashboard",
        "BindPaths": "/home/ubuntu/quant-dashboard/data",
        "PrivateTmp": "yes",
        "PrivateDevices": "yes",
        # No unix sockets: the docker socket (user ubuntu is in the docker group) and D-Bus.
        "RestrictAddressFamilies": "AF_INET AF_INET6",
        "IPAddressDeny": "any",
        "IPAddressAllow": "localhost",
        "SystemCallFilter": "@system-service",
    }
    for key, value in expected.items():
        assert unit.get(key) == value, key
    assert "RemoveIPC" not in unit  # it would remove the IPC objects of every ubuntu process
    # The tick's Toss token cache is not the web's to read.
    assert unit["InaccessiblePaths"].split() == [
        "-/home/ubuntu/quant-dashboard/data/backup",
        "-/home/ubuntu/quant-dashboard/data/autotrade-toss",
    ]
    assert "ReadWritePaths" not in unit  # data/ (BindPaths) is the only writable place
    assert "--host 127.0.0.1" in unit["ExecStart"]
    assert unit["StandardError"].startswith("append:/home/ubuntu/quant-dashboard/data/logs/")


def code_lines(text: str) -> str:
    """The text without its comment lines."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def nginx_cidrs(text: str) -> tuple[set[str], set[str]]:
    geo = re.search(r"geo \$realip_remote_addr \$quant_via_cloudflare \{(.*?)\}", text, re.S)
    assert geo is not None
    allowed = {
        line.split()[0]
        for line in geo.group(1).splitlines()
        if line.strip().endswith(" 1;") and not line.strip().startswith(("127.", "::1"))
    }
    trusted = set(re.findall(r"set_real_ip_from ([0-9a-f.:/]+);", text))
    return allowed, trusted


def test_nginx_lets_only_cloudflare_in_and_believes_only_cloudflare() -> None:
    text = code_lines((DEPLOY / "nginx-quant.conf").read_text())
    allowed, trusted = nginx_cidrs(text)
    assert len(allowed) == 22
    assert allowed == trusted  # one list of edges for both jobs
    assert text.count("if ($quant_via_cloudflare = 0)") == 2  # port 80 and 443
    assert "allow " not in text  # realip rewrites $remote_addr before allow/deny would run
    assert "deny " not in text
    assert text.count("server_tokens off;") == 2
    hsts = re.findall(r'add_header Strict-Transport-Security "([^"]+)" always;', text)
    assert hsts == ["max-age=31536000"]  # quant only: no includeSubDomains, no preload
    assert "proxy_set_header Host $host;" in text  # the app compares Origin with Host


def test_deploy_sh_order_and_syntax() -> None:
    script = (DEPLOY / "deploy.sh").read_text()
    subprocess.run(["bash", "-n", str(DEPLOY / "deploy.sh")], check=True)
    steps = [
        "helper web-build",  # 1. build outside the live tree
        "git pull --ff-only",  # 2. move the tree
        "autotrade.jobs migrate --predeploy",  # 4.-5. a fresh copy, then the only migration,
        # under the tick's and the AI runner's locks (one command: nothing falls between)
        "helper web-switch",  # 6. then the web
        "sudo systemctl restart autotrade.service",  # 7. then the API
    ]
    positions = [script.index(step, script.index('MODE="${1:-}"')) for step in steps]
    assert positions == sorted(positions)
    assert "reset --hard" not in script


def test_npm_installs_without_scripts() -> None:
    release = (REPO_ROOT / "autotrade" / "api" / "release.py").read_text()
    assert '"ci", "--ignore-scripts"' in release
    # Only release.py installs (without scripts); deploy.sh never calls npm itself.
    assert "npm " not in code_lines((DEPLOY / "deploy.sh").read_text())


def _install_cron() -> ModuleType:
    spec = importlib.util.spec_from_file_location("install_cron", DEPLOY / "install_cron.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_cron_replaces_only_the_quant_block() -> None:
    install = _install_cron()
    block = (DEPLOY / "autotrade.cron").read_text()
    assert block.startswith("# >>> quant (deploy/autotrade.cron) >>>\n")
    assert block.rstrip("\n").endswith("# <<< quant <<<")
    current = (
        "0 1 * * * other app\n"
        "# >>> quant (old) >>>\n*/5 * * * * old tick\n# <<< quant <<<\n"
        "# >>> portfolio >>>\n0 2 * * * portfolio job\n# <<< portfolio <<<\n"
    )
    new = install.replace_block(current, block)
    assert "old tick" not in new
    assert new.startswith("0 1 * * * other app\n# >>> quant (deploy/autotrade.cron) >>>\n")
    assert new.endswith("# >>> portfolio >>>\n0 2 * * * portfolio job\n# <<< portfolio <<<\n")
    jobs = [line for line in new.splitlines() if line and not line.startswith("#")]
    assert jobs == [
        "0 1 * * * other app",
        *[line for line in block.splitlines() if line and not line.startswith("#")],
        "0 2 * * * portfolio job",
    ]


def test_install_cron_refuses_instead_of_appending() -> None:
    install = _install_cron()
    block = "# >>> quant >>>\n*/5 * * * * tick\n# <<< quant <<<\n"
    with pytest.raises(SystemExit):  # no block in the crontab
        install.replace_block("0 1 * * * other app\n", block)
    two = "# >>> quant >>>\na\n# <<< quant <<<\n# >>> quant >>>\nb\n# <<< quant <<<\n"
    with pytest.raises(SystemExit):  # two blocks
        install.replace_block(two, block)
    with pytest.raises(SystemExit):  # a block file without its markers
        install.replace_block("# >>> quant >>>\na\n# <<< quant <<<\n", "*/5 * * * * tick\n")
    with pytest.raises(SystemExit):  # another app's block is not this one
        install.replace_block("# >>> quantx >>>\na\n# <<< quantx <<<\n", block)
