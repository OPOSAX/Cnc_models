# Post de la máquina (PowerMill)

`POST-4axis-table-B.opt` es el **postprocesador de PowerMill (DuctPost)** que entregó el fabricante. Es para un control Fanuc con un 4.º eje **B** en la mesa. En PowerMill se elige al escribir el NC.

## Qué salida produce
- **Inicio:** `%`, comentarios de fecha y versión, `G40 G17 G80 G49 G90` y, en programas que no son de 5 ejes, `M71` y `M73`.
- **Por herramienta:** comentarios de la fresa, cambio de herramienta, `S… M3`, `G0 G54 X… Y…`, `G43 H1` y `G90`.
- **Movimientos:** `G0` y `G1` con X Y Z, eje **B** y F. Son modales y sin arcos (lineales).
- **Final:** `G91 G28 Z0`, `M05`, `M08` y `M30`, cerrado con `%`.

## Qué nos dice
El ejemplo `rough-1.nc` del fabricante es la salida de este post **con las primeras líneas quitadas**: empieza en `N11 S1500 M3` y `N12 G0 G54 X… Y…`. Los números que faltan (N13, N17) son líneas borradas, como `G43 H1` y los comentarios. Además termina en `G53 Z0` en vez de `G91 G28 Z0`.

Los `.nc` de la lámpara y de Krea3D siguen el formato de `rough-1.nc`, que es lo que la máquina ya ha ejecutado. El programa de prueba (`../prueba_maquina`) añade además el inicio del post: `G40 G17 G80 G49 G90`, `M71`, `M73` y `G43 H1`. El `M08` del final del post no se usa.
