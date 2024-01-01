#include <stdio.h>
#include <limits.h>
#include <stdlib.h>
#include <libgen.h>
#include <errno.h>
#include <string.h>

#include "csv_plotter.h"

char *program;

static void usage(FILE *) __attribute__((noreturn));

int main(int argc, char **argv) {
    char *filename;
    program = basename(argv[0]);

    if (argc != 2)
        usage(stderr);

    if ((filename = realpath(argv[1], NULL)) == NULL) {
        error("Error getting realpath of %s: %s\n", argv[1], strerror(errno));
        exit(EXIT_FAILURE);
    }
    printf("realpath: %s\n", filename);

    exit(EXIT_SUCCESS);
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
