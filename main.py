import sys

from app.connector import run


def main() -> None:
    run(sys.argv[1:])


if __name__ == "__main__":
    main()
