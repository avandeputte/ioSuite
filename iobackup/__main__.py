"""`python -m iobackup`: ioBackup alone, as one copy of the program (iosuite_shared.host; `iosuite serve` runs several apps)."""
from iosuite_shared import host


def main():
    host.run(["iobackup"])


if __name__ == "__main__":
    main()
