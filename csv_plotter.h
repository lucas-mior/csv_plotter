#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#define LENGTH(x) (int) ((sizeof (x) / sizeof (*x)))

#ifndef INTEGERS
#define INTEGERS
typedef unsigned char uchar;
typedef unsigned short ushort;
typedef unsigned int uint;
typedef unsigned long ulong;
typedef unsigned long long ulonglong;

typedef int8_t int8;
typedef int16_t int16;
typedef int32_t int32;
typedef int64_t int64;
typedef uint8_t uint8;
typedef uint16_t uint16;
typedef uint32_t uint32;
typedef uint64_t uint64;

typedef size_t usize;
typedef ssize_t isize;
#endif

typedef struct File {
    FILE *file;
    char *name;
    void *map;
    int length;
    int fd;
} File;

extern char *program;
static const char SPLIT_CHAR = ',';

void error(char *, ...);
void *util_malloc(const size_t);
void *util_memdup(const void *, const size_t);
char *util_strdup(const char *);
void *util_realloc(void *, const size_t);
void *util_calloc(const size_t, const size_t);
int util_string_int32(int32 *, const char *);
void util_segv_handler(int) __attribute__((noreturn));
void util_close(File *);
int util_open(File *, const int);
