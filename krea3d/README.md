# Krea3D

App web para tallar **murales y relieves en CNC a partir de una imagen**.
Subes una imagen, indicas el tamaño del mural, la profundidad y las fresas, y genera los programas `.nc`
(desbaste + acabado) listos para la máquina. Todo se calcula en el navegador: no necesita servidor ni base de datos.

## Qué hace
- Imagen → relieve: claro = alto (sin tallar), oscuro = profundo (o al revés). Ajustes de contraste, niveles y suavizado.
- Vista previa del relieve sombreado, vista 3D girable y dibujo de la trayectoria de cada NC.
- **Desbaste** con fresa plana por niveles (paso vertical, paso lateral, sobremedida).
- **Acabado** con fresa bola, plana o en V, pasadas en X o en Y.
- Murales grandes: los divide en **paneles** (tamaño máximo configurable) y saca un NC por panel; las uniones casan porque se calculan sobre el relieve completo.
- Formato **Chaoda** (copiado del ejemplo del fabricante: `N`, `G54`, `G53 Z0`, `G0 M05`, `M30`, `%`, CRLF, sin arcos) o **genérico** (GRBL/Mach3).
- Cálculo de la fresa conservador: la herramienta nunca baja por debajo del relieve (verificado en pruebas con la geometría exacta de la fresa; el error máximo es la tolerancia de simplificación, 0.02 mm por defecto).
- Tiempo estimado por programa, descarga individual o todo en `.zip`.

Origen de cada NC: **X0 Y0 = esquina inferior izquierda del panel**, **Z0 = cara superior del tablero**.

## Archivos
| Archivo | Para qué |
|---|---|
| `index.html` | la página |
| `app.js` | interfaz |
| `core.js` | cálculo: relieve, fresa, trayectorias, G-code |
| `worker.js` | ejecuta el cálculo en segundo plano |

## Publicarlo en www.paolosaxton.com/krea3d
Sube **la carpeta `krea3d` completa** (los 4 archivos) a la raíz pública del sitio:

- **Hosting con cPanel / FTP** (Hostinger, GoDaddy, SiteGround…): Administrador de archivos → `public_html/` → crear carpeta `krea3d` → subir los 4 archivos. Queda en `https://www.paolosaxton.com/krea3d/`.
- **Netlify / Vercel / GitHub Pages**: copiar la carpeta `krea3d` dentro del proyecto publicado.
- **Wix / Squarespace / Shopify**: estos no permiten subir carpetas. Opciones: publicar Krea3D en un subdominio (`krea3d.paolosaxton.com`, por ejemplo con GitHub Pages o Netlify gratis) y enlazarlo desde el menú, o redirigir `/krea3d` a ese subdominio.

Debe servirse por `http(s)://` (no abriendo el archivo con doble clic) para que funcione el cálculo en segundo plano.
Usa desde CDN: three.js (vista 3D), JSZip (descarga .zip) y Google Fonts.

## Probar el núcleo
```bash
node -e "const K=require('./core.js'); console.log(Object.keys(K))"
```
