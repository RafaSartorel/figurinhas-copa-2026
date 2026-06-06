import sys

from update_stickers import main as update_stickers_main


def main() -> None:
    args = sys.argv[1:]

    if args and args[0].lower() == "remove":
        args = args[1:]

    update_stickers_main(["remove", *args])


if __name__ == "__main__":
    main()
