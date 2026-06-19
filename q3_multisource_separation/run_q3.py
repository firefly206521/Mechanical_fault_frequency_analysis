"""Direct launcher for the Q3 package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from q3_multisource_separation.cli import main


if __name__ == "__main__":
    main()

