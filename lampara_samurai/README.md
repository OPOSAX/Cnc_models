# Lámpara Samurái – piezas y programas CNC

Lámpara escultórica estilo samurái (sombrero cónico negro, kimono dorado, *hakama* negra) despiezada en tablero plano para router CNC.

![montaje](img/montaje.png)

**Medidas generales:** alto 767 mm (hasta la cara superior del botón) · base 330 × 220 mm · sombrero Ø440 mm.

## Piezas

![piezas](img/piezas.png)

| ID | Pieza | Cant. | Material | Medida (mm) | Color | Notas |
|---|---|---|---|---|---|---|
| P01 | Frente base (hakama) | 1 | MDF 15 | 330 × 340 | negro | ranura central 8 mm = dos "piernas" |
| P02 | Trasera base | 1 | MDF 15 | 330 × 340 | negro | muesca 24×14 salida de cable |
| P03 | Lateral base | 2 | MDF 15 | 190 × 341.2 | negro | va inclinado 8°, entre frente y trasera; apoya en el suelo por su arista interior (sin bisel) |
| P04 | Tapa base | 1 | MDF 15 | 238.2 × 224 | negro | ventana 80.5 para la columna |
| P05 | Collar columna | 2 | MDF 15 | 140 × 140 | negro | se encolan bajo la tapa |
| P06 | Columna frente/trasera | 2 | MDF 15 | 80 × 381.6 | negro | |
| P07 | Columna lateral | 2 | MDF 15 | 50 × 381.6 | negro | taladro Ø10 (cable LED); en una basta |
| P08 | Tapa columna | 1 | MDF 15 | 80 × 80 | negro | taladro Ø8 para inserto roscado M6 o tuerca de garras M6 |
| P09 | Sombrero (desarrollo del cono) | 1 | **Contrachapado flexible 3** | 491.9 × 491.9 | negro | sector 322° + tira de solape de 20 mm de ancho constante (línea marcada); agujero central Ø33.4 en el cono montado |
| P10 | Botón sombrero | 1 | MDF 15 | Ø50 | negro | taladro Ø7 |
| P11 | Buje sombrero | 1 | MDF 15 | Ø140 | negro | taladro Ø7; se encola bajo el cono (toca en r = 70); muesca de costura de 46 mm de ancho (fondo a 57.2 mm del centro) |
| P12 | Obi capa superior | 1 | MDF 15 | 230.1 × 79.5 | oro | 2 cajeras de 8 mm; *dogbones* en la muesca de la columna |
| P13 | Obi capa | 2 | MDF 15 | 230.1 × 79.5 | oro | *dogbones* en la muesca de la columna |
| P14 | Yugo hombros | 1 | MDF 15 | 223.6 × 103.5 | negro | cantos inclinados sujetan P15 |
| P15 | Solapa trasera (kimono) | 2 | MDF 15 | 115.4 × 308 | oro | cortar 2 iguales, la izquierda se voltea |
| P16 | Solapa delantera (cuello) | 2 | MDF 15 | 86 × 282 | oro | se encola sobre P15 |
| P17 | Buje superior sombrero | 1 | MDF 15 | Ø80 | negro | taladro Ø7; se encola sobre P11 (toca el cono en r = 40); muesca de costura de 46 mm de ancho (fondo a 24.5 mm del centro) |
| P18 | Separador botón | 1 | MDF 15 | Ø26 | negro | taladro Ø7; pasa por el agujero del cono |

Total: **25 piezas** (24 en MDF 15 mm — caben en un tablero de 1220 × 1220 — y 1 en contrachapado flexible 3 mm).
**P09 necesita una hoja de contrachapado de al menos 520 × 520 mm (recomendado 600 × 600):** la fresa trabaja de X/Y −3 a 494.9
(huella de corte de −6 a 497.9), y hay que dejar ≥ 10 mm entre esa huella y el borde de la hoja para sujetarla.
`python3 cam.py` imprime el tablero mínimo de cada pieza (huella de la fresa + 10 mm por lado).

Tira de solape de P09: mide 20 mm de ancho constante desde ~39 mm del vértice del desarrollo hacia fuera; junto al agujero
se estrecha (hasta ~4.4 mm) porque el hueco del sector es más estrecho que la tira y hay que dejar paso a la fresa.
Esa zona queda tapada por el botón.

**Muesca de costura en P11 y P17.** La tira de solape va pegada por dentro del cono, así que a lo largo de la costura la cara
interior queda 3 / cos 26.6° = 3.35 mm más baja. Sin más, la tira chocaría con el canto superior de P11 (banda r 63.3–70) y de
P17 (r 33.3–40) y el cono quedaría cojo junto a la costura. Por eso los dos bujes llevan una muesca pasante de 46 mm de ancho
(20 mm de tira + 3 mm de holgura, a cada lado de la costura, para que valga sea cual sea el lado hacia el que quede la tira) y
con el fondo a 57.2 mm (P11) y 24.5 mm (P17) del centro; el fondo es recto y ya tiene en cuenta que la tira se curva con el
cono. Las dos muescas van alineadas y la costura (línea marcada de P09) se coloca en el centro de la muesca. En el resto de la
circunferencia el cono sigue apoyando en r = 70 y r = 40. Se ajusta con `SEAM_ANG` (dirección de la costura, por defecto
atrás) y `SEAM_M` (holgura) en `geometria.py`.

## Programas NC (`nc/`)

Un `.nc` por pieza. **Formato copiado del ejemplo `.nc` que entrega el fabricante (Chaoda) para esta máquina:**
números de línea `N`, palabras separadas por espacio, `G90` y `S… M3` al inicio, primer movimiento `G0 G54 X… Y…`,
código modal (`X-.865 Z284.`), avance entero (`F1500`), sin comentarios, sin arcos G2/G3 (los taladros van en hélice con rectas),
final `G53 Z0` / `G0 M05` / `M30` / `%`, saltos de línea CRLF. No se programa el eje B (corte plano en 3 ejes).
Si una pieza tiene cantidad 2, se ejecuta el programa dos veces.

| Parámetro | Valor |
|---|---|
| Herramienta | T1 fresa plana Ø6 mm (2 cortes; compresión ideal en MDF) |
| Husillo | S18000 (el ejemplo del fabricante trae S1500: confirmar qué usa la máquina) |
| Avance XY / Z | 1500 / 500 mm/min (ejemplo del fabricante: 5000 / 1000) |
| Altura seguridad | Z10 |
| Pasada | máx. 5 mm: **4 pasadas de 3.825 mm** en MDF 15 (prof. 15.3); máx. 1.8 mm: **2 pasadas de 1.65 mm** en el contrachapado 3 (prof. 3.3) |
| Profundidad | espesor + 0.3 mm (al tablero mártir) |
| Puentes | 3–6 por pieza, 8 mm de ancho, **3 mm de alto en MDF (Z-12) y 1.2 mm en el sombrero (Z-1.8)**, medidos desde la cara inferior del tablero; solo en la última pasada y solo en tramos rectos o curvas suaves (nunca en los redondeos de esquina ni dentro de ranuras, muescas u otras concavidades del contorno: `cam.py` descarta todo tramo cuyo exterior queda dentro de la envolvente convexa de la pieza) |
| Origen | **X0 Y0 = esquina inferior izquierda de la pieza** (deja ≥10 mm entre la huella de la fresa —3 mm más allá de la trayectoria, 6 mm más allá de la pieza— y el borde del tablero) · **Z0 = cara superior del tablero**, todo en **G54** |

Orden dentro de cada programa: taladros (helicoidal) → marcado → cajeras → cortes interiores (con *dogbones* en las esquinas para que entre la pieza cuadrada) → contorno exterior en concordancia con puentes.
Las esquinas interiores del contorno exterior que reciben una pieza cuadrada (la muesca de la columna en P12/P13) también llevan *dogbone*.
El resto de esquinas interiores exteriores (ranura de P01, muesca de P02, hombro de la espiga de P15) quedan con radio 3 mm de la fresa, que no molesta.

`img/trayectorias.png` es el backplot leído de los propios `.nc` para verificarlos.
En `dxf/` está cada pieza en DXF (capas CORTE_EXT, CORTE_INT, CAJERA, TALADRO, MARCADO) por si prefieres generar el CAM en tu software (Aspire, Fusion, etc.).

## Montaje

1. **Base:** encolar P03 (inclinados) entre P01 y P02, con su arista interior inferior apoyada en la mesa (la exterior queda ~2 mm en el aire: es normal, solo se ve de lado). Encolar los dos P05 bajo P04 (centrados en la ventana) y P04 encima de las paredes.
2. **Columna:** caja con P06 (fuera) y P07 (dentro). Antes de encolar P08 arriba, meter en su taladro de Ø8 el inserto roscado M6 desde abajo (si tu inserto pide otro taladro, cambia `INSERT_D` en `geometria.py`), o poner una tuerca de garras M6 por debajo.
   Introducir la columna por la ventana de P04 hasta que su extremo inferior quede **enrasado con la cara inferior del collar bajo** (45 mm por debajo de la cara superior de P04). La base no tiene fondo y nada hace de tope: **apoyar la columna en un calzo de 310 mm** puesto en la mesa dentro de la base mientras seca la cola, y comprobar la escuadra.
3. **Obi:** apilar P13 + P13 + P12 (cajeras arriba), encajar alrededor del frente de la columna sobre P04.
4. **Yugo:** deslizar P14 por la columna y **apoyarlo en dos calzos de 250 mm puestos sobre P12** (400 → 650 mm, canto superior a 665). Encolarlo a la columna y retirar los calzos cuando seque.
5. **Kimono:** P16 encolado sobre la cara frontal de P15 (alineando bordes inferior e interior). La espiga de P15 entra en la cajera del obi y su cara trasera se encola al canto inclinado del yugo. La pieza izquierda es la misma volteada.
6. **Sombrero:** curvar P09 hasta la línea marcada y encolar la tira de solape por dentro (cono). Encolar P17 centrado sobre P11 con las dos muescas de costura alineadas; encolar el cono sobre los cantos de P11 (r = 70) y P17 (r = 40) con la costura en el centro de las muescas (hacia atrás), de forma que la tira de solape quede dentro de ellas — un cordón de cola o epoxi en el ángulo da más superficie.
   Atornillar con **M6 × 70**: P10 (botón) → P18 (separador, pasa por el agujero del cono) → P17 → P11 → inserto de P08. Toda la pila es MDF macizo (60 mm), así que el tornillo no carga el contrachapado del cono y entran 10 mm en el inserto.
   El botón apoya a la vez en P18 y en el borde del agujero del cono; bajo su canto queda una rendija de ~4 mm por la pendiente del cono. Desmontable para acceder a la luz.
7. **Luz:** tira LED COB 24 V blanca cálida (2700 K) alrededor de la columna entre 670–690 mm (bajo el sombrero), cable por el taladro de P07, por dentro de la columna hasta la fuente dentro de la base, salida por la muesca de P02.
8. **Acabado:** sellador para cantos de MDF, lijar, negro mate y dorado (o pan de oro) en P12, P13, P15, P16.

## Modificar el diseño

Todo es paramétrico (`geometria.py`: medidas; `cam.py`: herramienta, avances, puentes).

```bash
pip install -r requirements.txt
python3 geometria.py   # lista de piezas y total
python3 dibujos.py     # img/montaje.png e img/piezas.png
python3 cam.py         # nc/*.nc y dxf/*.dxf
python3 backplot.py    # img/trayectorias.png (verificación)
```
