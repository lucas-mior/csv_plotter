#include <stdio.h>
#include <stdlib.h>
#include <libgen.h>

#include "csv_plotter.h"

char *program;

int main(int argc, char **argv) {
    program = basename(argv[0]);
    printf("%s: main(%d)\n", program, argc);
    exit(EXIT_SUCCESS);
}
