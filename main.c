#include <stdio.h>
#include <stdlib.h>
#include <libgen.h>

#include "csv_plotter.h"

char *program;

static void usage(FILE *) __attribute__((noreturn));

int main(int argc, char **argv) {
    program = basename(argv[0]);

    if (argc != 2)
        usage(stderr);

    exit(EXIT_SUCCESS);
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
