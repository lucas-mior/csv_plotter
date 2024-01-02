#include <stdio.h>
#include <limits.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <libgen.h>
#include <errno.h>
#include <string.h>
#include <threads.h>
#include <gtk/gtk.h>

#include "csv_plotter.h"
#include "hash.h"

#define USE_THREADS_THRESHOLD 1024 

char *program;

static void usage(FILE *) __attribute__((noreturn));
static int count_separators(char *);
static int convert_arrays(void *);

/* Surface to store current scribbles */
static cairo_surface_t *surface = NULL;

static void
clear_surface (void)
{
  cairo_t *cr;

  cr = cairo_create (surface);

  cairo_set_source_rgb (cr, 1, 1, 1);
  cairo_paint (cr);

  cairo_destroy (cr);
}

/* Create a new surface of the appropriate size to store our scribbles */
static void
resize_cb (GtkWidget *widget,
           int        width,
           int        height,
           gpointer   data)
{
  if (surface)
    {
      cairo_surface_destroy (surface);
      surface = NULL;
    }

  if (gtk_native_get_surface (gtk_widget_get_native (widget)))
    {
      surface = gdk_surface_create_similar_surface (gtk_native_get_surface (gtk_widget_get_native (widget)),
                                                    CAIRO_CONTENT_COLOR,
                                                    gtk_widget_get_width (widget),
                                                    gtk_widget_get_height (widget));

      /* Initialize the surface to white */
      clear_surface ();
    }
}

/* Redraw the screen from the surface. Note that the draw
 * callback receives a ready-to-be-used cairo_t that is already
 * clipped to only draw the exposed areas of the widget
 */
static void
draw_cb (GtkDrawingArea *drawing_area,
         cairo_t        *cr,
         int             width,
         int             height,
         gpointer        data)
{
  cairo_set_source_surface (cr, surface, 0, 0);
  cairo_paint (cr);
}

/* Draw a rectangle on the surface at the given position */
static void
draw_brush (GtkWidget *widget,
            double     x,
            double     y)
{
  cairo_t *cr;

  /* Paint to the surface, where we store our state */
  cr = cairo_create (surface);

  cairo_rectangle (cr, x - 3, y - 3, 6, 6);
  cairo_fill (cr);

  cairo_destroy (cr);

  /* Now invalidate the drawing area. */
  gtk_widget_queue_draw (widget);
}

static double start_x;
static double start_y;

static void
drag_begin (GtkGestureDrag *gesture,
            double          x,
            double          y,
            GtkWidget      *area)
{
  start_x = x;
  start_y = y;

  draw_brush (area, x, y);
}

static void
drag_update (GtkGestureDrag *gesture,
             double          x,
             double          y,
             GtkWidget      *area)
{
  draw_brush (area, start_x + x, start_y + y);
}

static void
drag_end (GtkGestureDrag *gesture,
          double          x,
          double          y,
          GtkWidget      *area)
{
  draw_brush (area, start_x + x, start_y + y);
}

static void
pressed (GtkGestureClick *gesture,
         int              n_press,
         double           x,
         double           y,
         GtkWidget       *area)
{
  clear_surface ();
  gtk_widget_queue_draw (area);
}

static void
close_window (void)
{
  if (surface)
    cairo_surface_destroy (surface);
}

static void
activate (GtkApplication *app,
          gpointer        user_data)
{
  GtkWidget *window;
  GtkWidget *frame;
  GtkWidget *drawing_area;
  GtkGesture *drag;
  GtkGesture *press;

  window = gtk_application_window_new (app);
  gtk_window_set_title (GTK_WINDOW (window), "Drawing Area");

  g_signal_connect (window, "destroy", G_CALLBACK (close_window), NULL);

  frame = gtk_frame_new (NULL);
  gtk_window_set_child (GTK_WINDOW (window), frame);

  drawing_area = gtk_drawing_area_new ();
  /* set a minimum size */
  gtk_widget_set_size_request (drawing_area, 100, 100);

  gtk_frame_set_child (GTK_FRAME (frame), drawing_area);

  gtk_drawing_area_set_draw_func (GTK_DRAWING_AREA (drawing_area), draw_cb, NULL, NULL);

  g_signal_connect_after (drawing_area, "resize", G_CALLBACK (resize_cb), NULL);

  drag = gtk_gesture_drag_new ();
  gtk_gesture_single_set_button (GTK_GESTURE_SINGLE (drag), GDK_BUTTON_PRIMARY);
  gtk_widget_add_controller (drawing_area, GTK_EVENT_CONTROLLER (drag));
  g_signal_connect (drag, "drag-begin", G_CALLBACK (drag_begin), drawing_area);
  g_signal_connect (drag, "drag-update", G_CALLBACK (drag_update), drawing_area);
  g_signal_connect (drag, "drag-end", G_CALLBACK (drag_end), drawing_area);

  press = gtk_gesture_click_new ();
  gtk_gesture_single_set_button (GTK_GESTURE_SINGLE (press), GDK_BUTTON_SECONDARY);
  gtk_widget_add_controller (drawing_area, GTK_EVENT_CONTROLLER (press));

  g_signal_connect (press, "pressed", G_CALLBACK (pressed), drawing_area);

  gtk_window_present (GTK_WINDOW (window));
}

typedef struct Slice {
    FloatArray **arrays;
    int start;
    int end;
} Slice;

int main(int argc, char **argv) {
    /* File file = {0}; */
    /* program = basename(argv[0]); */
    /* int lines = 0; */

    /* if (argc != 2) */
    /*     usage(stderr); */

    /* file.name = argv[1]; */
    /* if ((file.fd = open(file.name, O_RDONLY)) < 0) { */
    /*     error("Error opening %s for reading: %s\n", file.name, strerror(errno)); */
    /*     exit(EXIT_FAILURE); */
    /* } */

    /* { */
    /*     struct stat file_stat; */
    /*     if (fstat(file.fd, &file_stat) < 0) { */
    /*         error("Error getting file information: %s\n", strerror(errno)); */
    /*         util_close(&file); */
    /*         exit(EXIT_FAILURE); */
    /*     } */
    /*     file.length = (usize) file_stat.st_size; */
    /*     if (file.length <= 0) { */
    /*         error("file.length: %zu\n", file.length); */
    /*         util_close(&file); */
    /*         exit(EXIT_FAILURE); */
    /*     } */
    /* } */

    /* file.map = mmap(NULL, file.length, */
    /*                 PROT_READ | PROT_WRITE, MAP_PRIVATE, */
    /*                 file.fd, 0); */
    /* if (file.map == MAP_FAILED) { */
    /*     error("Error mapping file file to memory: %s", strerror(errno)); */
    /*     util_close(&file); */
    /*     exit(EXIT_FAILURE); */
    /* } */

    /* int data_begin = (int) strcspn(file.map, "\n"); */
    /* file.map[data_begin] = '\0'; */
    /* int number_columns_headers = count_separators(file.map); */ 

    /* HashMap *columns_map = hash_map_create(number_columns_headers); */
    /* FloatArray **arrays_in_order = util_calloc(number_columns_headers, sizeof (*arrays_in_order)); */ 

    /* for (char *p = &file.map[data_begin+1]; p < (file.map + file.length); p += 1) { */
    /*     if (*p == '\n') */
    /*         lines += 1; */
    /* } */

    /* { */
    /*     char *p = file.map; */
    /*     for (int i = 0; i < number_columns_headers; i += 1) { */
    /*         char *name = strtok(p, SPLIT_CHAR); */
    /*         FloatArray *array = util_calloc(1, sizeof (*array)); */

    /*         array->name = util_strdup(name); */
    /*         hash_map_insert(columns_map, array->name, array); */
    /*         arrays_in_order[i] = array; */

    /*         array->texts = util_malloc((size_t) lines * sizeof (*&(array->texts))); */
    /*         array->array = util_malloc((size_t) lines * sizeof (*&(array->array))); */

    /*         p = NULL; */
    /*     } */
    /* } */
    /* hash_map_print(columns_map, true); */

    /* int line_length = 0; */
    /* int line = 0; */
    /* for (char *p = &file.map[data_begin+1]; */
    /*      p < (file.map + file.length); */
    /*      p += (line_length + 1)) { */

    /*     line_length = (int) strcspn(p, "\n"); */
    /*     p[line_length] = '\0'; */

    /*     int number_columns = count_separators(p); */
    /*     if (number_columns != number_columns_headers) { */
    /*         error("Wrong number of separators on line %d\n", line + 1); */
    /*         exit(EXIT_FAILURE); */
    /*     } */

    /*     char *value = p; */
    /*     for (int i = 0; i < number_columns_headers; i += 1) { */
    /*         int n = (int) strcspn(value, SPLIT_CHAR); */
    /*         arrays_in_order[i]->texts[line] = value; */

    /*         value[n] = '\0'; */
    /*         value += n + 1; */
    /*     } */

    /*     line += 1; */
    /* } */

    /* long number_threads = sysconf(_SC_NPROCESSORS_ONLN); */

    /* if ((lines >= USE_THREADS_THRESHOLD) && (number_threads >= 2)) { */
    /*     Slice *slices; */
    /*     thrd_t *threads; */
    /*     int range; */

    /*     if (number_columns_headers < number_threads) { */
    /*         number_threads = number_columns_headers; */
    /*         range = 1; */
    /*     } else { */
    /*         range = number_columns_headers / number_threads; */
    /*     } */

    /*     slices = util_malloc(number_threads * sizeof (*slices)); */
    /*     threads = util_malloc(number_threads * sizeof (*threads)); */


    /*     for (int i = 0; i < number_threads; i += 1) { */
    /*         slices[i].start = i*range; */
    /*         if (i == number_threads - 1) */
    /*             slices[i].end = number_columns_headers; */
    /*         else */
    /*             slices[i].end = (i + 1)*range; */
    /*         slices[i].arrays = arrays_in_order; */
    /*         thrd_create(&threads[i], convert_arrays, (void *) &slices[i]); */
    /*     } */

    /*     for (int i = 0; i < number_threads; i += 1) */
    /*         thrd_join(threads[i], NULL); */
    /* } else { */
    /*     for (int i = 0; i < number_columns_headers; i += 1) { */
    /*         for (int j = 0; j < lines; j += 1) */
    /*             arrays_in_order[i]->array[j] = atof(arrays_in_order[i]->texts[j]); */
    /*     } */
    /* } */
    /* for (int i = 0; i < number_columns_headers; i += 1) { */
    /*     printf("\n%s ======\n", arrays_in_order[i]->name); */
    /*     free(arrays_in_order[i]->texts); */
    /*     for (int j = 0; j < 10; j += 1) { */
    /*         printf("%i = %f\n", j, arrays_in_order[i]->array[j]); */
    /*     } */
    /* } */
    /* printf("\ngetting q_f =====\n"); */
    /* FloatArray *q_f; */
    /* if ((q_f = hash_map_lookup(columns_map, "q_f")) == NULL) { */
    /*     error("Error getting q_f column!\n"); */
    /*     exit(EXIT_FAILURE); */
    /* } */
    /* for (int j = 0; j < lines; j += 1) { */
    /*     printf("q_f(%i) = %f\n", j, q_f->array[j]); */
    /* } */


    /* if (munmap(file.map, file.length) < 0) { */
    /*     error("Error unmapping %p with %zu bytes: %s\n", */
    /*           (void *) file.map, file.length, strerror(errno)); */
    /* } */

    /* util_close(&file); */

    GtkApplication *app;
    int status;

    app = gtk_application_new ("org.gtk.example", G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect (app, "activate", G_CALLBACK (activate), NULL);
    status = g_application_run (G_APPLICATION (app), argc, argv);
    g_object_unref (app);

    exit(EXIT_SUCCESS);
}

int
convert_arrays(void *arg) {
    Slice *slice = arg;

    for (uint32 i = slice->start; i < slice->end; i += 1) {
    }

    thrd_exit(0);
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
