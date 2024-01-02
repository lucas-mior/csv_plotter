/*
 * Copyright (C) 2023 Mior, Lucas; <lucasbuddemior@gmail.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef HASH_H
#define HASH_H

#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct HashMap HashMap;

#ifndef INTEGERS
#define INTEGERS
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

HashMap *hash_map_create(uint32 length);
void hash_map_destroy(HashMap *map);
uint32 hash_function(char *str);
bool hash_map_insert(HashMap *map, char *key, void *value);
bool hash_map_insert_pre_calc(HashMap *map, char *key, uint32 hash, uint32 index, void *value);
void *hash_map_lookup(HashMap *map, char *key);
void *hash_map_lookup_pre_calc(HashMap *map, char *key, uint32 hash, uint32 index);
bool hash_map_remove(HashMap *map, char *key);
bool hash_map_remove_pre_calc(HashMap *map, char *key, uint32 hash, uint32 index);
void hash_map_print_summary(HashMap *map);
void hash_map_print(HashMap *map, bool verbose);
uint32 hash_map_capacity(HashMap *map);
uint32 hash_map_length(HashMap *map);
uint32 hash_map_collisions(HashMap *map);
uint32 hash_map_expected_collisions(HashMap *map);

#endif
