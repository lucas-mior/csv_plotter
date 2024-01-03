import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def error(message):
    print(f"{program}: {message}", file=sys.stderr)
    return


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <file.csv>", file=sys.stderr);
        exit(1);

    program = sys.argv[0]
    filename = sys.argv[1]
    df = None
    try:
        df = pd.read_csv(filename)
    except Exception:
        error(f"Error reading {filename}")
        exit(1)
    if df is None:
        error(f"Error reading {filename}")
        exit(1)

    x = df.iloc[:, 0]
    for column in df.columns:
        if column != x.name:
            y = df[column]
            plt.plot(x, y, label=column)

    plt.xlabel('X-axis Label')
    plt.ylabel('Y-axis Label')
    plt.title('Your Plot Title')
    plt.legend()
    plt.show()
