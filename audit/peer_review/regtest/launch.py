"""Start the pinned server after bootstrap.py. Secrets remain in RUNTIME only."""
from bootstrap import RUNTIME, IMAGES, docker, start, core
import json
import time


def captain(*args, check=True):
    return docker("run", "--rm", "--memory", "512m", "--cpus", "2", "--network", "host", "-v", f"{RUNTIME}:/data",
                  "--entrypoint", "captaind", IMAGES["captain"],
                  "--config", "/data/config/captaind.toml", *args, check=check)


def rpc(*args, check=True):
    return docker("exec", "spiral-captaind", "captaind", "rpc", "--addr", "127.0.0.1:13536", *args, check=check)


def bark(*args, check=True):
    return docker("exec", "spiral-bark", "bark", "--datadir", "/data", *args, check=check)


def main():
    if core("getblockcount") < 101:
        address = core("getnewaddress")
        core("generatetoaddress", "101", address)
    if not (RUNTIME / "captain/mnemonic").exists():
        result = captain("create", check=False)
        (RUNTIME / "logs/captain-create.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("captaind create failed; inspect private log")
    start("spiral-captaind", IMAGES["captain"], "captaind",
          ["--config", "/data/config/captaind.toml", "start"], [(RUNTIME, "/data")])
    for _ in range(20):
        result = rpc("wallet", check=False)
        if result.returncode == 0:
            (RUNTIME / "evidence/initial-server-wallet.json").write_text(result.stdout)
            print(result.stdout)
            break
        time.sleep(1)
    else:
        raise RuntimeError("captaind readiness timeout; inspect container logs")
    (RUNTIME / "bark").mkdir(exist_ok=True)
    start("spiral-bark", IMAGES["bark"], "/bin/sleep", ["infinity"], [(RUNTIME / "bark", "/data")])
    if not (RUNTIME / "bark/mnemonic").exists():
        result = bark("create", "--regtest", "--ark", "http://127.0.0.1:13535",
                      "--bitcoind", "http://127.0.0.1:18483", "--bitcoind-user", "spiral",
                      "--bitcoind-pass", "owned-regtest-only", check=False)
        (RUNTIME / "logs/bark-create.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Bark create failed; inspect private log")
    print(bark("balance").stdout)


if __name__ == "__main__":
    main()
