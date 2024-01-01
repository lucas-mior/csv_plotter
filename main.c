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

    if ((file.fd = open(file.name, O_RDONLY)) < 0) {
        error("Error opening %s for reading: %s\n", file.name, strerror(errno));
        exit(EXIT_FAILURE);
    }

    {
        struct stat file_stat;
        if (fstat(file.fd, &file_stat) < 0) {
            error("Error getting file information: %s\n", strerror(errno));
            util_close(&file);
            exit(EXIT_FAILURE);
        }
        file.length = (usize) file_stat.st_size;
        if (file.length <= 0) {
            error("file_length: %zu\n", file.length);
            util_close(&file);
            exit(EXIT_FAILURE);
        }
    }

    file.map = mmap(NULL, file.length, 
                    PROT_READ | PROT_WRITE, MAP_PRIVATE,
                    file.fd, 0);
    if (file.map == MAP_FAILED) {
        error("Error mapping file file to memory: %s", strerror(errno));
        util_close(&file);
        exit(EXIT_FAILURE);
    }

    if (munmap(file.map, file.length) < 0) {
        error("Error unmapping %p with %zu bytes: %s\n",
              (void *) file.map, file.length, strerror(errno));
    }
    util_close(&file);

    exit(EXIT_SUCCESS);
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
