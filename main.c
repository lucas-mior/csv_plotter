#include <stdio.h>
#include <limits.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <libgen.h>
#include <errno.h>
#include <string.h>

#include "csv_plotter.h"

char *program;

static void usage(FILE *) __attribute__((noreturn));

int main(int argc, char **argv) {
    File file = {0};
    program = basename(argv[0]);

    if (argc != 2)
        usage(stderr);

    if ((file.name = realpath(argv[1], NULL)) == NULL) {
        error("Error getting realpath of %s: %s\n", argv[1], strerror(errno));
        exit(EXIT_FAILURE);
    }
    printf("realpath: %s\n", file.name);

    if ((file.file = fopen(file.name, "r")) == NULL) {
        error("Error opening %s for reading: %s\n", file.name, strerror(errno));
        exit(EXIT_FAILURE);
    }

    char buffer[BUFSIZ];
    while (fgets(buffer, sizeof (buffer), file.file)) {
        printf("fgets: %s\n", buffer);
    }

    util_close(&file);
    exit(EXIT_SUCCESS);
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
