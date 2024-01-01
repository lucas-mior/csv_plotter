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
static int count_separators(char *);

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
    if (fgets(buffer, sizeof (buffer), file.file) == NULL) {
        error("Error reading from file: %s\n", strerror(errno));
        exit(EXIT_FAILURE);
    }
    int number_columns_headers = count_separators(buffer); 
    int line = 1;

    while (fgets(buffer, sizeof (buffer), file.file)) {
        int number_columns = count_separators(buffer);
        int length = strcspn(buffer, "\n"); 

        if (number_columns != number_columns_headers) {
            error("Wrong number of separators on line %d\n", line + 1);
            exit(EXIT_FAILURE);
        }
        printf("columns_headers: %d\n", number_columns);
        line += 1;
    }

    util_close(&file);
    exit(EXIT_SUCCESS);
}

int count_separators(char *string) {
    int count = 0;
    while (*string) {
        if (*string == SPLIT_CHAR)
            count += 1;

        string += 1;
    }
    return count;
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
