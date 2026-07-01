import sys

from app.connector import run
from app.runtime_bootstrap import ensure_preferred_python


def main() -> None:
    ensure_preferred_python(sys.argv[1:])
    run(sys.argv[1:])


if __name__ == "__main__":
    main()
