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
#include "hash.h"

#define INITIAL_DATA_LENGTH 128 

char *program;

static void usage(FILE *) __attribute__((noreturn));
static int count_separators(char *);

int main(int argc, char **argv) {
    File file = {0};
    program = basename(argv[0]);

    if (argc != 2)
        usage(stderr);

    file.name = argv[1];
    if ((file.file = fopen(file.name, "r")) == NULL) {
        error("Error opening %s for reading: %s\n", file.name, strerror(errno));
        exit(EXIT_FAILURE);
    }

    char buffer[BUFSIZ];
    if (fgets(buffer, sizeof (buffer), file.file) == NULL) {
        error("Error reading from file: %s\n", strerror(errno));
        exit(EXIT_FAILURE);
    }
    buffer[strcspn(buffer, "\n")] = '\0';
    int number_columns_headers = count_separators(buffer); 
    int line = 1;

    HashMap *columns_map = hash_map_create(number_columns_headers);
    FloatArray **arrays_in_order = util_calloc(number_columns_headers, sizeof (FloatArray *)); 

    {
        char *p = buffer;
        for (int i = 0; i < number_columns_headers; i += 1) {
            char *name;
            FloatArray *array;

            name = strtok(p, SPLIT_CHAR);
            array = util_calloc(1, sizeof *array);

            array->name = util_strdup(name);
            hash_map_insert(columns_map, array->name, array);
            arrays_in_order[i] = array;

            array->texts = util_calloc(INITIAL_DATA_LENGTH, sizeof (char *));
            p = NULL;
        }
    }
    hash_map_print(columns_map, true);

    while (fgets(buffer, sizeof (buffer), file.file)) {
        int number_columns = count_separators(buffer);
        char *p = buffer;

        if (number_columns != number_columns_headers) {
            error("Wrong number of separators on line %d\n", line + 1);
            exit(EXIT_FAILURE);
        }

        for (int i = 0; i < number_columns_headers; i += 1) {
            char *value = strtok(p, SPLIT_CHAR);
            arrays_in_order[i]->texts[line-1] = util_strdup(value);
            p = NULL;
        }

        line += 1;
    }
    for (int i = 0; i < number_columns_headers; i += 1) {
        arrays_in_order[i]->array = util_malloc(line * sizeof (float));
        for (int j = 0; j < (line - 1); j += 1) {
            arrays_in_order[i]->array[j] = atof(arrays_in_order[i]->texts[j]);
            printf("%i %i = %s = %f\n", i, j, arrays_in_order[i]->texts[j], arrays_in_order[i]->array[j]);
        }
    }

    util_close(&file);
    exit(EXIT_SUCCESS);
}

int count_separators(char *string) {
    int count = 0;
    while (*string) {
        if (*string == *SPLIT_CHAR)
            count += 1;

        string += 1;
    }
    return count + 1;
}

void usage(FILE *stream) {
    fprintf(stream, "usage: %s <file.csv>\n", program);
    exit(stream != stdout);
}
