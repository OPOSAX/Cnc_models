# Krea3D

App web para tallar **murales y relieves en CNC a partir de una imagen**.
Subes una imagen, indicas el tamaño del mural, la profundidad y las fresas, y la app genera los programas `.nc`
(desbaste y acabado) para la máquina. Todo se calcula en el navegador, sin servidor ni base de datos.

## Qué hace
- Imagen → relieve: claro = alto (sin tallar), oscuro = profundo (o al revés). Ajustes de contraste, niveles y suavizado.
  Si la imagen es enorme (más de 16 Mpx u 8192 px de lado), se reduce al cargarla y la app lo avisa.
- Vista previa del relieve sombreado, vista 3D girable y dibujo de la trayectoria de cada NC.
- **Desbaste** con fresa plana por niveles (paso vertical, paso lateral, sobremedida).
- **Acabado** con fresa bola, plana o en V, con pasadas en X o en Y.
- Murales grandes: los divide en **paneles** (tamaño máximo configurable, en mm; mínimo 50 mm) y saca un NC por panel.
  Avisa si salen más de 100 paneles y no deja generar si salen más de 1000 (suele ser el panel escrito en metros).
  Cada panel se calcula **solo con su material**: se supone que el tablero de cada panel está cortado a su tamaño.
  En las uniones entre paneles (y en los bordes del mural si no hay marco) el centro de la fresa **sale del borde hasta
  su radio**, para que el borde quede igual que en una pieza entera; las pasadas caen en la misma rejilla en todos los
  paneles, y así las uniones casan. Por eso, con fresa bola o en V, en esas uniones y bordes la punta puede bajar
  **por debajo de la profundidad máxima** (fuera del panel, en el aire si el tablero está cortado a medida); si el tablero
  es más grande que el panel, ese sobrepaso marcará el material de alrededor. Con **marco** activado, en los bordes
  exteriores la fresa no sale del mural y el material de fuera se trata como tablero a Z0.
  El número de paneles de la vista previa se calcula con la misma rejilla que usa el cálculo (alto real = filas × mm/px).
- Formato **Chaoda** (sigue el ejemplo del fabricante: `N`, `G54`, `G53 Z0`, `G0 M05`, `M30`, `%`, CRLF, sin arcos) o **genérico** (GRBL/Mach3).
- Valida todos los campos antes de generar (vacíos, cero, negativos, Z de traslado ≥ Z de seguridad…). Mientras haya un error, **Generar NC** queda deshabilitado y el campo se marca en rojo.
- Muestra una cota del tamaño del NC más grande y avisa si puede pasar de unos 150 MB.
- Si cambias parámetros o la imagen después de generar, los resultados se marcan como desactualizados y se bloquean su descarga, los botones **Ver** y la pestaña Trayectoria hasta que vuelvas a generar (o vuelvas a los valores anteriores).
- Tiempo estimado por programa; descarga individual o todo en `.zip`.

Origen de cada NC: **X0 Y0 = esquina inferior izquierda del panel**, **Z0 = cara superior del tablero**, `G54`.

## Archivos
| Ruta | Para qué |
|---|---|
| `index.html` | la página (estilos incluidos) |
| `app.js` | interfaz: parámetros, validación, vista previa, descargas |
| `core.js` | cálculo: relieve, fresa, trayectorias, G-code. Sin dependencias; funciona en navegador y en Node |
| `worker.js` | ejecuta `core.js` en segundo plano para que la página no se congele |
| `test/` | pruebas del núcleo en Node (`test/run.js`). No hace falta subirla a la web |

## Publicarlo en www.paolosaxton.com/krea3d
Sube a una carpeta `krea3d` en la raíz pública del sitio estos 4 archivos: `index.html`, `app.js`, `core.js` y `worker.js`
(la carpeta `test/` no es necesaria).

- **Hosting con cPanel / FTP** (Hostinger, GoDaddy, SiteGround…): Administrador de archivos → `public_html/` → crear la carpeta `krea3d` → subir los 4 archivos. Queda en `https://www.paolosaxton.com/krea3d/`.
- **Netlify / Vercel / GitHub Pages**: copiar la carpeta `krea3d` dentro del proyecto que se publica.
- **Wix / Squarespace / Shopify**: no permiten subir carpetas. Opciones: publicar Krea3D en un subdominio (por ejemplo `krea3d.paolosaxton.com` con GitHub Pages o Netlify) y enlazarlo desde el menú, o redirigir `/krea3d` a ese subdominio.

Hay que abrirla por `http(s)://`, no con doble clic sobre el archivo. Si no, el navegador no deja arrancar `worker.js` y el cálculo se hace en la propia página, que se queda congelada mientras tanto.
Para probarla en tu ordenador: `python3 -m http.server` dentro de la carpeta `krea3d` y abrir `http://localhost:8000/`.

Carga desde CDN three.js (vista 3D), JSZip (descarga `.zip`) y Google Fonts. Sin conexión siguen funcionando el cálculo y las descargas individuales;
solo faltan la vista 3D y el botón del `.zip`.

## Pruebas
Lo verificado del núcleo (el cálculo, el formato del NC y la validación de parámetros) se puede reproducir con:

```bash
node krea3d/test/run.js
```

desde la raíz del repositorio. Solo necesita Node; no usa paquetes externos.

Antes de cortar: revisa la trayectoria en la app, haz una pasada en vacío con Z0 unos 20 mm por encima del tablero y prueba primero en un retazo.
