#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <stdarg.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <stdint.h>

#include "csv_plotter.h"

void
error(char *format, ...) {
    int n;
    va_list args;
    char buffer[BUFSIZ];

    va_start(args, format);
    n = vsnprintf(buffer, sizeof (buffer) - 1, format, args);
    va_end(args);

    if (n < 0) {
        fprintf(stderr, "Error in vsnprintf()\n");
        exit(EXIT_FAILURE);
    }

    buffer[n] = '\0';
    write(STDERR_FILENO, buffer, (size_t) n);

#ifdef DEBUGGING
    switch (fork()) {
        char *notifiers[2] = { "dunstify", "notify-send" };
        case -1:
            fprintf(stderr, "Error forking: %s\n", strerror(errno));
            break;
        case 0:
            for (uint i = 0; i < LENGTH(notifiers); i += 1) {
                execlp(notifiers[i], notifiers[i], "-u", "critical", 
                                     program, buffer, NULL);
            }
            fprintf(stderr, "Error trying to exec dunstify.\n");
            break;
        default:
            break;
    }
    exit(EXIT_FAILURE);
#endif
}

void *
util_malloc(const size_t size) {
    void *p;
    if ((p = malloc(size)) == NULL) {
        error("Error allocating %zu bytes.\n", size);
        exit(EXIT_FAILURE);
    }
    return p;
}

void *
util_memdup(const void *source, const size_t size) {
    void *p;
    if ((p = malloc(size)) == NULL) {
        error("Error allocating %zu bytes.\n", size);
        exit(EXIT_FAILURE);
    }
    memcpy(p, source, size);
    return p;
}

char *
util_strdup(const char *string) {
    char *p;
    size_t size;

    size = strlen(string) + 1;
    if ((p = malloc(size)) == NULL) {
        error("Error allocating %zu bytes.\n", size);
        exit(EXIT_FAILURE);
    }

    memcpy(p, string, size);
    return p;
}

void *
util_realloc(void *old, const size_t size) {
    void *p;
    if ((p = realloc(old, size)) == NULL) {
        error("Error reallocating %zu bytes.\n", size);
        error("Reallocating from: %p\n", old);
        exit(EXIT_FAILURE);
    }
    return p;
}

void *
util_calloc(const size_t nmemb, const size_t size) {
    void *p;
    if ((p = calloc(nmemb, size)) == NULL) {
        error("Error allocating %zu members of %zu bytes each.\n",
                        nmemb, size);
        exit(EXIT_FAILURE);
    }
    return p;
}

int
util_string_int32(int32 *number, const char *string) {
    char *endptr;
    long x;
    errno = 0;
    x = strtol(string, &endptr, 10);
    if ((errno != 0) || (string == endptr) || (*endptr != 0)) {
        return -1;
    } else if ((x > INT32_MAX) || (x < INT32_MIN)) {
        return -1;
    } else {
        *number = (int32) x;
        return 0;
    }
}

void
util_segv_handler(int unused) {
    char *message = "Memory error. Please send a bug report.\n";
    char *notifiers[2] = { "dunstify", "notify-send" };
    (void) unused;

    (void) write(STDERR_FILENO, message, strlen(message));
    for (uint i = 0; i < LENGTH(notifiers); i += 1) {
        execlp(notifiers[i], notifiers[i], "-u", "critical", 
                             "clipsim", message, NULL);
    }
    _exit(EXIT_FAILURE);
}

void
util_close(File *file) {
    if (file->fd >= 0) {
        if (close(file->fd) < 0) {
            error("Error closing %s: %s\n",
                            file->name, strerror(errno));
        }
        file->fd = -1;
    }
    if (file->file != NULL) {
        if (fclose(file->file) != 0) {
            error("Error closing %s: %s\n",
                            file->name, strerror(errno));
        }
        file->file = NULL;
    }
    return;
}

int
util_open(File *file, const int flag) {
    if ((file->fd = open(file->name, flag)) < 0) {
        error("Error opening %s: %s\n",
                        file->name, strerror(errno));
        return -1;
    } else {
        return 0;
    }
}
